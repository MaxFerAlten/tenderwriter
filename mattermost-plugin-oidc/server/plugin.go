package main

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/coreos/go-oidc/v3/oidc"
	"github.com/mattermost/mattermost/server/public/model"
	"github.com/mattermost/mattermost/server/public/plugin"
	"golang.org/x/oauth2"
)

const (
	kvStatePrefix = "oidc_state_"
	stateTTL      = 300 // 5 minutes
)

// Plugin implements the Mattermost plugin interface for OIDC authentication.
type Plugin struct {
	plugin.MattermostPlugin

	mu           sync.RWMutex
	oauth2Config *oauth2.Config
	idVerifier   *oidc.IDTokenVerifier
	initialized  bool
}

// OnActivate is called when the plugin is activated. It initializes the OIDC
// provider lazily — if Keycloak isn't ready yet, initialization is retried on
// the first request.
func (p *Plugin) OnActivate() error {
	cfg := p.getConfiguration()
	if !cfg.Enable {
		p.API.LogInfo("TW-OIDC plugin loaded but DISABLED (TW_OIDC_ENABLE != true)")
		return nil
	}

	p.API.LogInfo("TW-OIDC plugin activating",
		"discovery", cfg.DiscoveryEndpoint,
		"client_id", cfg.ClientID,
	)

	// Try to initialize now; if Keycloak isn't up yet we'll retry lazily.
	if err := p.initOIDC(cfg); err != nil {
		p.API.LogWarn("TW-OIDC deferred initialization (Keycloak may not be ready yet)", "error", err.Error())
	}
	return nil
}

// OnConfigurationChange is called when plugin settings are changed via System Console.
func (p *Plugin) OnConfigurationChange() error {
	cfg := p.getConfiguration()
	if cfg.Enable {
		if err := p.initOIDC(cfg); err != nil {
			p.API.LogWarn("TW-OIDC re-initialization failed", "error", err.Error())
		}
	}
	return nil
}

func (p *Plugin) initOIDC(cfg *Configuration) error {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	discovery, err := fetchDiscoveryDocument(ctx, cfg.DiscoveryEndpoint)
	if err != nil {
		return fmt.Errorf("oidc discovery failed: %w", err)
	}

	siteURL := ""
	if sc := p.API.GetConfig().ServiceSettings.SiteURL; sc != nil {
		siteURL = *sc
	}

	authURL := discovery.AuthorizationEndpoint
	tokenURL := rewriteBackchannelURL(discovery.TokenEndpoint, cfg.PublicBaseURL, cfg.InternalBaseURL)
	jwksURL := rewriteBackchannelURL(discovery.JWKSURI, cfg.PublicBaseURL, cfg.InternalBaseURL)

	oauth2Cfg := &oauth2.Config{
		ClientID:     cfg.ClientID,
		ClientSecret: cfg.ClientSecret,
		RedirectURL:  siteURL + "/plugins/com.tenderwriter.oidc/callback",
		Endpoint: oauth2.Endpoint{
			AuthURL:  authURL,
			TokenURL: tokenURL,
		},
		Scopes:       []string{oidc.ScopeOpenID, "email", "profile"},
	}

	keySet := oidc.NewRemoteKeySet(ctx, jwksURL)
	idVerifier := oidc.NewVerifier(discovery.Issuer, keySet, &oidc.Config{
		ClientID: cfg.ClientID,
	})

	p.mu.Lock()
	p.oauth2Config = oauth2Cfg
	p.idVerifier = idVerifier
	p.initialized = true
	p.mu.Unlock()

	p.API.LogInfo(
		"TW-OIDC initialized successfully",
		"redirect_url", oauth2Cfg.RedirectURL,
		"auth_url", authURL,
		"token_url", tokenURL,
		"jwks_url", jwksURL,
		"issuer", discovery.Issuer,
	)
	return nil
}

func (p *Plugin) ensureInitialized() error {
	p.mu.RLock()
	ready := p.initialized
	p.mu.RUnlock()
	if ready {
		return nil
	}
	cfg := p.getConfiguration()
	if !cfg.Enable {
		return fmt.Errorf("plugin is disabled")
	}
	return p.initOIDC(cfg)
}

// ---------------------------------------------------------------------------
// HTTP Router
// ---------------------------------------------------------------------------

func (p *Plugin) ServeHTTP(c *plugin.Context, w http.ResponseWriter, r *http.Request) {
	switch r.URL.Path {
	case "/login":
		p.handleLogin(w, r)
	case "/callback":
		p.handleCallback(w, r)
	case "/health":
		p.handleHealth(w)
	default:
		http.NotFound(w, r)
	}
}

// ---------------------------------------------------------------------------
// /login — start OIDC flow with PKCE
// ---------------------------------------------------------------------------

type statePayload struct {
	Verifier   string `json:"v"`
	RedirectTo string `json:"r"`
}

func (p *Plugin) handleLogin(w http.ResponseWriter, r *http.Request) {
	if err := p.ensureInitialized(); err != nil {
		http.Error(w, "OIDC not initialized: "+err.Error(), http.StatusServiceUnavailable)
		return
	}

	redirectTo := r.URL.Query().Get("redirect_to")
	if redirectTo == "" || !strings.HasPrefix(redirectTo, "/") || strings.HasPrefix(redirectTo, "//") {
		redirectTo = "/"
	}

	state := randomString(32)
	verifier := randomString(64)

	payload, _ := json.Marshal(statePayload{
		Verifier:   verifier,
		RedirectTo: redirectTo,
	})

	if appErr := p.API.KVSetWithExpiry(kvStatePrefix+state, payload, stateTTL); appErr != nil {
		p.API.LogError("TW-OIDC failed to store state", "error", appErr.Error())
		http.Error(w, "Internal error", http.StatusInternalServerError)
		return
	}

	challenge := sha256PKCE(verifier)

	p.mu.RLock()
	authURL := p.oauth2Config.AuthCodeURL(state,
		oauth2.SetAuthURLParam("code_challenge", challenge),
		oauth2.SetAuthURLParam("code_challenge_method", "S256"),
	)
	p.mu.RUnlock()

	http.Redirect(w, r, authURL, http.StatusFound)
}

// ---------------------------------------------------------------------------
// /callback — exchange code, create user + session, set cookie
// ---------------------------------------------------------------------------

func (p *Plugin) handleCallback(w http.ResponseWriter, r *http.Request) {
	if errMsg := r.URL.Query().Get("error"); errMsg != "" {
		desc := r.URL.Query().Get("error_description")
		p.API.LogWarn("TW-OIDC callback error from IdP", "error", errMsg, "description", desc)
		http.Error(w, "Authentication error: "+errMsg, http.StatusForbidden)
		return
	}

	code := r.URL.Query().Get("code")
	state := r.URL.Query().Get("state")
	if code == "" || state == "" {
		http.Error(w, "Missing code or state", http.StatusBadRequest)
		return
	}

	// Retrieve and delete state
	raw, appErr := p.API.KVGet(kvStatePrefix + state)
	if appErr != nil || raw == nil {
		http.Error(w, "Invalid or expired state", http.StatusBadRequest)
		return
	}
	_ = p.API.KVDelete(kvStatePrefix + state)

	var sp statePayload
	if err := json.Unmarshal(raw, &sp); err != nil {
		http.Error(w, "Corrupt state data", http.StatusInternalServerError)
		return
	}

	// Exchange code for tokens
	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	p.mu.RLock()
	cfg := p.oauth2Config
	idVerifier := p.idVerifier
	p.mu.RUnlock()

	token, err := cfg.Exchange(ctx, code,
		oauth2.SetAuthURLParam("code_verifier", sp.Verifier),
	)
	if err != nil {
		p.API.LogError("TW-OIDC token exchange failed", "error", err.Error())
		http.Error(w, "Token exchange failed", http.StatusInternalServerError)
		return
	}

	// Verify ID token
	rawIDToken, ok := token.Extra("id_token").(string)
	if !ok {
		http.Error(w, "No id_token in response", http.StatusInternalServerError)
		return
	}

	idToken, err := idVerifier.Verify(ctx, rawIDToken)
	if err != nil {
		p.API.LogError("TW-OIDC id_token verification failed", "error", err.Error())
		http.Error(w, "Token verification failed", http.StatusInternalServerError)
		return
	}

	var claims struct {
		Email      string `json:"email"`
		Name       string `json:"name"`
		GivenName  string `json:"given_name"`
		FamilyName string `json:"family_name"`
		Username   string `json:"preferred_username"`
		Sub        string `json:"sub"`
	}
	if err := idToken.Claims(&claims); err != nil {
		http.Error(w, "Failed to read claims", http.StatusInternalServerError)
		return
	}
	if claims.Email == "" {
		http.Error(w, "No email in token claims", http.StatusForbidden)
		return
	}

	// Find or create Mattermost user
	user, appErr := p.API.GetUserByEmail(claims.Email)
	if appErr != nil {
		if appErr.StatusCode != http.StatusNotFound {
			p.API.LogError("TW-OIDC user lookup failed", "email", claims.Email, "error", appErr.Error())
			http.Error(w, "Failed to lookup user", http.StatusInternalServerError)
			return
		}

		// User doesn't exist — create
		username := sanitizeUsername(claims.Username, claims.Email)
		user = &model.User{
			Email:     claims.Email,
			Username:  username,
			FirstName: claims.GivenName,
			LastName:  claims.FamilyName,
			Password:  "TW!" + randomString(32),
			EmailVerified: true,
		}
		user, appErr = p.API.CreateUser(user)
		if appErr != nil {
			p.API.LogError("TW-OIDC user creation failed",
				"email", claims.Email, "error", appErr.Error())
			http.Error(w, "Failed to create user: "+appErr.Error(), http.StatusInternalServerError)
			return
		}
		p.API.LogInfo("TW-OIDC user created", "email", claims.Email, "mm_id", user.Id)

		// Add to first available team
		if teams, err := p.API.GetTeams(); err == nil && len(teams) > 0 {
			if _, err := p.API.CreateTeamMember(teams[0].Id, user.Id); err != nil {
				p.API.LogWarn("TW-OIDC team membership failed", "error", err.Error())
			}
		}
	} else {
		// Sync profile fields from IdP (non-destructive)
		changed := false
		if claims.GivenName != "" && user.FirstName != claims.GivenName {
			user.FirstName = claims.GivenName
			changed = true
		}
		if claims.FamilyName != "" && user.LastName != claims.FamilyName {
			user.LastName = claims.FamilyName
			changed = true
		}
		if changed {
			if _, err := p.API.UpdateUser(user); err != nil {
				p.API.LogWarn("TW-OIDC user sync failed", "error", err.Error())
			}
		}
	}

	// Create session
	session := &model.Session{
		UserId:    user.Id,
		Roles:     user.GetRawRoles(),
		IsOAuth:   true,
		Props: model.StringMap{
			"platform": "tw-oidc-plugin",
			"os":       "Keycloak SSO",
		},
	}

	session, appErr = p.API.CreateSession(session)
	if appErr != nil {
		p.API.LogError("TW-OIDC session creation failed", "error", appErr.Error())
		http.Error(w, "Session creation failed", http.StatusInternalServerError)
		return
	}

	// Determine cookie path from SiteURL subpath
	cookiePath := "/"
	siteURL := ""
	if sc := p.API.GetConfig().ServiceSettings.SiteURL; sc != nil {
		siteURL = *sc
	}
	if idx := strings.Index(siteURL, "://"); idx > 0 {
		rest := siteURL[idx+3:]
		if slashIdx := strings.Index(rest, "/"); slashIdx > 0 {
			cookiePath = rest[slashIdx:]
		}
	}
	isSecure := strings.HasPrefix(siteURL, "https")

	// Set auth cookies
	http.SetCookie(w, &http.Cookie{
		Name:     "MMAUTHTOKEN",
		Value:    session.Token,
		Path:     cookiePath,
		HttpOnly: true,
		Secure:   isSecure,
		SameSite: http.SameSiteLaxMode,
	})
	http.SetCookie(w, &http.Cookie{
		Name:     "MMUSERID",
		Value:    user.Id,
		Path:     cookiePath,
		Secure:   isSecure,
		SameSite: http.SameSiteLaxMode,
	})
	http.SetCookie(w, &http.Cookie{
		Name:     "MMCSRF",
		Value:    session.GetCSRF(),
		Path:     cookiePath,
		Secure:   isSecure,
		SameSite: http.SameSiteLaxMode,
	})

	p.API.LogInfo("TW-OIDC login successful",
		"email", claims.Email,
		"mm_user", user.Id,
		"redirect", sp.RedirectTo,
	)

	http.Redirect(w, r, sp.RedirectTo, http.StatusFound)
}

// ---------------------------------------------------------------------------
// /health — simple liveness check
// ---------------------------------------------------------------------------

func (p *Plugin) handleHealth(w http.ResponseWriter) {
	p.mu.RLock()
	ready := p.initialized
	p.mu.RUnlock()

	cfg := p.getConfiguration()

	w.Header().Set("Content-Type", "application/json")
	status := map[string]interface{}{
		"plugin":      "com.tenderwriter.oidc",
		"version":     "1.0.0",
		"enabled":     cfg.Enable,
		"initialized": ready,
	}
	json.NewEncoder(w).Encode(status)
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

func randomString(n int) string {
	b := make([]byte, n)
	_, _ = rand.Read(b)
	return base64.RawURLEncoding.EncodeToString(b)
}

type discoveryDocument struct {
	Issuer                string `json:"issuer"`
	AuthorizationEndpoint string `json:"authorization_endpoint"`
	TokenEndpoint         string `json:"token_endpoint"`
	JWKSURI               string `json:"jwks_uri"`
}

func fetchDiscoveryDocument(ctx context.Context, discoveryURL string) (*discoveryDocument, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, discoveryURL, nil)
	if err != nil {
		return nil, err
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return nil, fmt.Errorf("unexpected discovery status %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}

	var doc discoveryDocument
	if err := json.NewDecoder(resp.Body).Decode(&doc); err != nil {
		return nil, err
	}

	if doc.Issuer == "" || doc.AuthorizationEndpoint == "" || doc.TokenEndpoint == "" || doc.JWKSURI == "" {
		return nil, fmt.Errorf("incomplete discovery document")
	}

	return &doc, nil
}

func rewriteBackchannelURL(rawURL, publicBaseURL, internalBaseURL string) string {
	publicBase := strings.TrimRight(publicBaseURL, "/")
	internalBase := strings.TrimRight(internalBaseURL, "/")
	if publicBase == "" || internalBase == "" {
		return rawURL
	}

	if strings.HasPrefix(rawURL, publicBase) {
		return internalBase + strings.TrimPrefix(rawURL, publicBase)
	}

	return rawURL
}

func sha256PKCE(verifier string) string {
	h := sha256.Sum256([]byte(verifier))
	return base64.RawURLEncoding.EncodeToString(h[:])
}

func sanitizeUsername(preferred, email string) string {
	name := preferred
	if name == "" {
		name = strings.Split(email, "@")[0]
	}
	// Mattermost usernames: 3-22 chars, lowercase, [a-z0-9._-]
	var b strings.Builder
	for _, c := range strings.ToLower(name) {
		if (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_' {
			b.WriteRune(c)
		}
	}
	result := b.String()
	if len(result) < 3 {
		result = result + "-kc"
	}
	if len(result) > 22 {
		result = result[:22]
	}
	return result
}
