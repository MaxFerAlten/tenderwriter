/** Buddy companion types. */

export interface BuddyStats {
  xp: number;
  level: number;
  happiness: number;
  energy: number;
}

export interface Buddy {
  id: string;
  name: string;
  species: "cat" | "dog" | "rabbit" | "owl" | "dragon";
  rarity: "common" | "rare" | "epic" | "legendary";
  stats: BuddyStats;
  mood: "happy" | "neutral" | "thinking" | "sleeping";
  accessory: string | null;
}

export interface BuddyNotification {
  id: string;
  type: "xp" | "achievement" | "level_up" | "birthday";
  message: string;
  timestamp: number;
}