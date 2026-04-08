/** BuddySprite — animated companion sprite component. */

import { useState, useEffect } from "react";
import type { Buddy } from "./types";

interface Props {
  buddy: Buddy;
  size?: number;
  showMood?: boolean;
}

export function BuddySprite({ buddy, size = 64, showMood = true }: Props) {
  const [animating, setAnimating] = useState(false);

  useEffect(() => {
    if (buddy.mood === "thinking" || buddy.mood === "happy") {
      setAnimating(true);
      const t = setTimeout(() => setAnimating(false), 2000);
      return () => clearTimeout(t);
    }
  }, [buddy.mood]);

  const getEmoji = () => {
    const base = { cat: "🐱", dog: "🐕", rabbit: "🐰", owl: "🦉", dragon: "🐉" };
    const moods: Record<string, Record<string, string>> = {
      cat: { happy: "😸", neutral: "🐱", thinking: "🤔", sleeping: "😴" },
      dog: { happy: "🐶", neutral: "🐕", thinking: "🐕", sleeping: "💤" },
      rabbit: { happy: "🐰", neutral: "🐇", thinking: "🤔", sleeping: "💤" },
      owl: { happy: "🦉", neutral: "🦅", thinking: "🦉", sleeping: "🌙" },
      dragon: { happy: "🐲", neutral: "🐉", thinking: "🐲", sleeping: "💤" },
    };
    return moods[buddy.species]?.[buddy.mood] || base[buddy.species];
  };

  return (
    <div className="relative inline-flex flex-col items-center">
      <span
        className={`inline-block ${animating ? "animate-bounce" : ""}`}
        style={{ fontSize: size }}
        role="img"
        aria-label={`${buddy.name} the ${buddy.species}`}
      >
        {getEmoji()}
      </span>
      
      {/* Level badge */}
      <div className="absolute -bottom-1 -right-1 px-1.5 py-0.5 bg-zinc-800 rounded-full text-xs font-bold text-zinc-300 border border-zinc-600">
        {buddy.stats.level}
      </div>
      
      {/* Mood indicator */}
      {showMood && (
        <div className="absolute -top-1 -left-1">
          {buddy.mood === "thinking" && <span className="text-xs">💭</span>}
          {buddy.mood === "happy" && <span className="text-xs">✨</span>}
        </div>
      )}
    </div>
  );
}