/** BuddyPanel — companion stats and interactions panel. */

import { useState } from "react";
import { X, Heart, Zap, Trophy } from "lucide-react";
import { BuddySprite } from "./BuddySprite";
import type { Buddy } from "./types";

interface Props {
  buddy: Buddy | null;
  isOpen: boolean;
  onClose: () => void;
}

export function BuddyPanel({ buddy, isOpen, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<"stats" | "achievements">("stats");

  if (!isOpen || !buddy) return null;

  const xpToNextLevel = buddy.stats.level * 100;
  const xpProgress = (buddy.stats.xp % xpToNextLevel) / xpToNextLevel * 100;

  return (
    <div className="fixed right-4 top-20 w-72 bg-zinc-900 rounded-xl border border-zinc-700 shadow-xl z-40">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-700">
        <h3 className="font-semibold text-zinc-100">Your Companion</h3>
        <button onClick={onClose} className="p-1 hover:bg-zinc-800 rounded">
          <X className="w-4 h-4 text-zinc-400" />
        </button>
      </div>

      {/* Buddy display */}
      <div className="flex flex-col items-center py-6 border-b border-zinc-700">
        <BuddySprite buddy={buddy} size={80} />
        <h4 className="mt-2 font-bold text-zinc-100">{buddy.name}</h4>
        <p className="text-sm text-zinc-500 capitalize">{buddy.rarity} {buddy.species}</p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-zinc-700">
        <button
          onClick={() => setActiveTab("stats")}
          className={`flex-1 py-2 text-sm font-medium ${
            activeTab === "stats" ? "text-blue-400 border-b-2 border-blue-400" : "text-zinc-500"
          }`}
        >
          Stats
        </button>
        <button
          onClick={() => setActiveTab("achievements")}
          className={`flex-1 py-2 text-sm font-medium ${
            activeTab === "achievements" ? "text-blue-400 border-b-2 border-blue-400" : "text-zinc-500"
          }`}
        >
          Achievements
        </button>
      </div>

      {/* Content */}
      <div className="p-4">
        {activeTab === "stats" && (
          <div className="space-y-4">
            {/* XP Bar */}
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-zinc-400">Level {buddy.stats.level}</span>
                <span className="text-zinc-500">{buddy.stats.xp % xpToNextLevel}/{xpToNextLevel} XP</span>
              </div>
              <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-blue-500 to-purple-500 transition-all"
                  style={{ width: `${xpProgress}%` }}
                />
              </div>
            </div>

            {/* Stat bars */}
            <div className="space-y-3">
              <StatBar icon={<Heart className="w-4 h-4 text-red-400" />} label="Happiness" value={buddy.stats.happiness} />
              <StatBar icon={<Zap className="w-4 h-4 text-yellow-400" />} label="Energy" value={buddy.stats.energy} />
            </div>
          </div>
        )}

        {activeTab === "achievements" && (
          <div className="space-y-2">
            <Achievement title="First Steps" description="Use your first command" unlocked />
            <Achievement title="Helper" description="Complete 10 tasks" unlocked />
            <Achievement title="Expert" description="Complete 50 tasks" unlocked={false} />
          </div>
        )}
      </div>
    </div>
  );
}

function StatBar({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="flex items-center gap-3">
      {icon}
      <div className="flex-1">
        <div className="flex justify-between text-xs mb-1">
          <span className="text-zinc-400">{label}</span>
          <span className="text-zinc-500">{value}%</span>
        </div>
        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
          <div className="h-full bg-zinc-500" style={{ width: `${value}%` }} />
        </div>
      </div>
    </div>
  );
}

function Achievement({ title, description, unlocked }: { title: string; description: string; unlocked: boolean }) {
  return (
    <div className={`flex items-center gap-3 p-2 rounded-lg ${unlocked ? "bg-zinc-800" : "bg-zinc-900 opacity-50"}`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center ${unlocked ? "bg-amber-500/20" : "bg-zinc-700"}`}>
        <Trophy className={`w-4 h-4 ${unlocked ? "text-amber-400" : "text-zinc-500"}`} />
      </div>
      <div>
        <p className="text-sm font-medium text-zinc-300">{title}</p>
        <p className="text-xs text-zinc-500">{description}</p>
      </div>
    </div>
  );
}