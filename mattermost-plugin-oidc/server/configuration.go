package main

import (
	"os"
	"strings"
	"sync"
)

// Configuration holds the plugin settings, resolved from env vars first, then
// plugin settings schema (System Console), then defaults.
type Configuration struct {
	Enable            bool   `json:"Enable"`
	DiscoveryEndpoint string `json:"DiscoveryEndpoint"`
	ClientID          string `json:"ClientID"`
	ClientSecret      string `json:"ClientSecret"`
	ButtonText        string `json:"ButtonText"`
	PublicBaseURL     string `json:"PublicBaseURL"`
	InternalBaseURL   string `json:"InternalBaseURL"`
}

var (
	configOnce sync.Once
	cachedCfg  *Configuration
)

func (p *Plugin) getConfiguration() *Configuration {
	// Env vars take precedence — this lets docker-compose control the plugin
	// without touching the System Console.
	envEnable := os.Getenv("TW_OIDC_ENABLE")
	envDiscovery := os.Getenv("TW_OIDC_DISCOVERY_ENDPOINT")
	envClientID := os.Getenv("TW_OIDC_CLIENT_ID")
	envSecret := os.Getenv("TW_OIDC_CLIENT_SECRET")
	envButton := os.Getenv("TW_OIDC_BUTTON_TEXT")
	envPublicBase := os.Getenv("TW_OIDC_PUBLIC_BASE_URL")
	envInternalBase := os.Getenv("TW_OIDC_INTERNAL_BASE_URL")

	cfg := &Configuration{
		Enable:            strings.EqualFold(envEnable, "true"),
		DiscoveryEndpoint: envDiscovery,
		ClientID:          envClientID,
		ClientSecret:      envSecret,
		ButtonText:        envButton,
		PublicBaseURL:     envPublicBase,
		InternalBaseURL:   envInternalBase,
	}

	// Fall back to plugin settings from System Console
	var stored Configuration
	if err := p.API.LoadPluginConfiguration(&stored); err == nil {
		if cfg.DiscoveryEndpoint == "" {
			cfg.DiscoveryEndpoint = stored.DiscoveryEndpoint
		}
		if cfg.ClientID == "" {
			cfg.ClientID = stored.ClientID
		}
		if cfg.ClientSecret == "" {
			cfg.ClientSecret = stored.ClientSecret
		}
		if cfg.ButtonText == "" {
			cfg.ButtonText = stored.ButtonText
		}
		if cfg.PublicBaseURL == "" {
			cfg.PublicBaseURL = stored.PublicBaseURL
		}
		if cfg.InternalBaseURL == "" {
			cfg.InternalBaseURL = stored.InternalBaseURL
		}
		if envEnable == "" {
			cfg.Enable = stored.Enable
		}
	}

	// Defaults
	if cfg.DiscoveryEndpoint == "" {
		cfg.DiscoveryEndpoint = "http://keycloak:8080/realms/tenderwriter/.well-known/openid-configuration"
	}
	if cfg.ClientID == "" {
		cfg.ClientID = "mattermost"
	}
	if cfg.ButtonText == "" {
		cfg.ButtonText = "Accedi con Keycloak"
	}
	if cfg.PublicBaseURL == "" {
		cfg.PublicBaseURL = "http://localhost:8180"
	}
	if cfg.InternalBaseURL == "" {
		cfg.InternalBaseURL = "http://keycloak:8080"
	}

	return cfg
}
