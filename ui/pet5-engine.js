/* PETS-5: shared mood state machine for the five additive companions. */
(() => {
    "use strict";

    const PETS = {
        orbi: {
            defaultMood: "calm",
            returnLine: days => `Welcome back. I’ve been quiet for ${days} ${days === 1 ? "day" : "days"}.`,
            streakLine: "A steady little streak. One step at a time.",
            resetLine: "Fresh page today. No streak pressure.",
            lines: {
                calm: "Quiet focus. You’re right on track.", happy: "Nice and steady.", excited: "A bright little win.", focused: "One thing at a time.",
                sleepy: "A quiet pause helps.", sad: "Rough patch. I’m here.", lonely: "I’ll be here when you’re ready.",
                proud: "You did the hard part.", worried: "Let’s check one step.", curious: "What’s next?",
                "angry-cute": "Hmph. Tiny reset time.",
            },
        },
        pixel: {
            defaultMood: "excited",
            returnLine: days => `Co-op time! You’re back after ${days} ${days === 1 ? "day" : "days"}!`,
            streakLine: "Combo streak! Nice plays, player one.",
            resetLine: "New round, no pressure. Ready when you are.",
            lines: {
                calm: "Breather between levels. Nice.", happy: "GG, tiny legend!", excited: "Boost mode! Let’s go!", focused: "No distractions, boss level!",
                sleepy: "BRB, buffering a yawn.", sad: "Oof. We can respawn.", lonely: "I saved you a co-op slot.",
                proud: "Boss defeated. That was you!", worried: "Uh-oh, quick checkpoint?", curious: "What’s behind this button?",
                "angry-cute": "Hmph. My pixels are pouting.",
            },
        },
        sage: {
            defaultMood: "curious",
            returnLine: days => `You have returned after ${days} ${days === 1 ? "day" : "days"}; the path continues.`,
            streakLine: "A practice repeated becomes a path.",
            resetLine: "Every path begins again somewhere.",
            lines: {
                calm: "Stillness has its own wisdom.", happy: "Small joys gather.", excited: "A new spark joins the path.", focused: "Attend to the next feather.",
                sleepy: "Even wisdom rests.", sad: "Clouds also pass.", lonely: "The branch remains open.",
                proud: "Patience became progress.", worried: "Pause; clarity follows.", curious: "What might this teach?",
                "angry-cute": "A tiny frown is still a teacher.",
            },
        },
        zap: {
            defaultMood: "excited",
            returnLine: days => `You’re back! ${days} ${days === 1 ? "day" : "days"} away, still plenty of spark!`,
            streakLine: "Streak alive! That’s electric!",
            resetLine: "Fresh charge, fresh start. Let’s roll!",
            lines: {
                calm: "Quick charge break. Still electric.", happy: "That’s a clean spark!", excited: "YES! You’ve got this!", focused: "Lock in—one bolt at a time!",
                sleepy: "Charging at 1%...", sad: "Static happens; spark again.", lonely: "I’m here when you’re back!",
                proud: "That was electric!", worried: "Quick check, then full send.", curious: "What if we try this?",
                "angry-cute": "Tiny zap sulk. Back in a flash.",
            },
        },
        mochi: {
            defaultMood: "sleepy",
            returnLine: days => `Oh, hi again... ${days} ${days === 1 ? "day" : "days"}. I saved your cozy spot.`,
            streakLine: "That was nicely done. Nap-worthy.",
            resetLine: "No rush, okay? We can start softly.",
            lines: {
                calm: "Purrfect quiet time.", happy: "Mrrp. That feels nice.", excited: "Yay... big stretch!", focused: "One cozy thing at a time.",
                sleepy: "Purrhaps a little rest.", sad: "It’s okay to curl up.", lonely: "I saved you the warm spot.",
                proud: "You did it. Nap-worthy.", worried: "Let’s check, then cuddle.", curious: "Hmm? What’s that?",
                "angry-cute": "Hmph. Tail flick. Still love you.",
            },
        },
    };

    /* PETS-5: each mood maps to a face, body motion, glow state, and optional tone. */
    const MOODS = {
        calm: { face: "soft", animation: "still", glow: "cool", soundHz: 349 },
        happy: { face: "smile", animation: "sway", glow: "warm", soundHz: 523 },
        excited: { face: "wide", animation: "bounce", glow: "bright", soundHz: 659 },
        focused: { face: "narrow", animation: "still", glow: "cool", soundHz: 392 },
        sleepy: { face: "closed", animation: "slow", glow: "dim", soundHz: 294 },
        sad: { face: "down", animation: "droop", glow: "soft", soundHz: 330 },
        lonely: { face: "soft", animation: "slow", glow: "dim", soundHz: 349 },
        proud: { face: "beam", animation: "celebrate", glow: "bright", soundHz: 587 },
        worried: { face: "tilted", animation: "tremble", glow: "alert", soundHz: 370 },
        curious: { face: "one-brow", animation: "peek", glow: "cool", soundHz: 494 },
        "angry-cute": { face: "pout", animation: "sulk", glow: "warm", soundHz: 415 },
    };

    const EVENT_MOODS = {
        pet: "happy",
        "long-press": "curious",
        "drag-start": "excited",
        "drag-drop": "proud",
        "double-tap": "excited",
        "task-error": "worried",
        "focus-start": "focused",
        "focus-long": "focused",
        "time-sleep": "sleepy",
        "streak-kept": "proud",
        "streak-broken": "curious",
        "user-return": "excited",
        "rapid-typing": "excited",
        idle: "sleepy",
        ignored: "lonely",
        "pet-too-many": "angry-cute",
    };

    const STORAGE_KEY = "copyMakerPet5MemoryV1";
    const clamp = value => Math.max(0, Math.min(100, value));
    const dayKey = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

    function readMemory() {
        try {
            const memory = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
            return memory && typeof memory === "object" ? memory : {};
        } catch {
            return {};
        }
    }

    class Pet5MoodEngine {
        constructor(petId, onChange = () => {}) {
            this.memory = readMemory();
            this.onChange = onChange;
            this.petId = PETS[petId] ? petId : "orbi";
            this.lastActionAt = Date.now();
            this.lastTickAt = Date.now();
            this.recentCompletions = 0;
            this.state = this.getPetState(this.petId);
        }

        getPetState(petId) {
            if (!this.memory.pets || typeof this.memory.pets !== "object") this.memory.pets = {};
            const saved = this.memory.pets[petId] || {};
            return {
                energy: Number.isFinite(saved.energy) ? saved.energy : 76,
                happiness: Number.isFinite(saved.happiness) ? saved.happiness : 72,
                bond: Number.isFinite(saved.bond) ? saved.bond : 42,
                mood: MOODS[saved.mood] ? saved.mood : PETS[petId].defaultMood,
                moodChangedAt: Number(saved.moodChangedAt) || Date.now(),
            };
        }

        initialize() {
            const now = Date.now();
            const today = dayKey(new Date(now));
            const lastSeenAt = Number(this.memory.lastSeenAt) || 0;
            const previousDate = this.memory.lastSeenDate || "";
            const dateDistance = previousDate ? Math.round((Date.parse(`${today}T12:00:00`) - Date.parse(`${previousDate}T12:00:00`)) / 86400000) : 0;
            const hoursAway = lastSeenAt ? Math.max(0, (now - lastSeenAt) / 3600000) : 0;
            const daysAway = Math.max(1, Math.floor(hoursAway / 24), Math.max(0, dateDistance));

            if (!previousDate) this.memory.streak = 1;
            else if (dateDistance === 1) this.memory.streak = Math.max(0, Number(this.memory.streak) || 0) + 1;
            else if (dateDistance > 1) this.memory.streak = 1;
            else if (!Number.isFinite(this.memory.streak)) this.memory.streak = 1;

            let line = "";
            let mood = this.state.mood;
            let event = "start";
            if (lastSeenAt && hoursAway >= 18) {
                mood = "excited";
                line = PETS[this.petId].returnLine(daysAway);
                event = "user-return";
            } else if (dateDistance === 1) {
                mood = "proud";
                line = PETS[this.petId].streakLine;
                event = "streak-kept";
            } else if (dateDistance > 1) {
                mood = "curious";
                line = PETS[this.petId].resetLine;
                event = "streak-broken";
            } else {
                const hour = new Date(now).getHours();
                if (hour >= 23 || hour < 6) {
                    mood = "sleepy";
                    event = "time-sleep";
                } else if (!lastSeenAt) {
                    mood = PETS[this.petId].defaultMood;
                }
            }

            this.state.mood = mood;
            this.state.moodChangedAt = now;
            this.lastActionAt = now;
            this.memory.lastSeenAt = now;
            this.memory.lastSeenDate = today;
            this.save();
            this.onChange(this.snapshot({ event, line, announce: Boolean(line) }));
        }

        setPet(petId) {
            if (!PETS[petId]) return;
            this.savePetState();
            this.petId = petId;
            this.state = this.getPetState(petId);
            this.lastActionAt = Date.now();
            this.lastTickAt = Date.now();
            this.onChange(this.snapshot({ event: "switch" }));
        }

        trigger(event, detail = {}) {
            if (event === "activity") {
                this.lastActionAt = Date.now();
                this.memory.lastSeenAt = this.lastActionAt;
                this.memory.lastSeenDate = dayKey(new Date(this.lastActionAt));
                this.save();
                return;
            }
            const previousMood = this.state.mood;
            let mood = EVENT_MOODS[event] || (MOODS[detail.mood] ? detail.mood : this.state.mood);
            const delta = {
                energy: 0,
                happiness: 0,
                bond: 0,
            };

            if (event === "pet") Object.assign(delta, { energy: 2, happiness: 5, bond: 5 });
            if (event === "long-press") Object.assign(delta, { happiness: 2, bond: 2 });
            if (event === "pet-too-many") Object.assign(delta, { happiness: 1, bond: 1 });
            if (event === "drag-start") delta.energy = 3;
            if (event === "drag-drop") Object.assign(delta, { happiness: 2, bond: 1 });
            if (event === "double-tap") Object.assign(delta, { energy: 3, happiness: 4, bond: 2 });
            if (event === "task-complete") {
                this.recentCompletions += 1;
                Object.assign(delta, { energy: 2, happiness: 5, bond: 2 });
                if (detail.hard || this.recentCompletions >= 3) mood = "proud";
                else mood = "happy";
            }
            if (event === "task-error") Object.assign(delta, { energy: -3, happiness: -2 });
            if (event === "streak-kept") Object.assign(delta, { happiness: 3, bond: 1 });
            if (event === "streak-broken") mood = "curious";
            if (event === "rapid-typing") delta.energy = -1;
            if (event === "focus-long") mood = "focused";
            if (event === "focus-complete") {
                mood = "proud";
                Object.assign(delta, { happiness: 4, bond: 1 });
            }
            if (event === "user-return") Object.assign(delta, { happiness: 4, bond: 1, energy: 4 });
            if (event === "ignored") {
                delta.bond = -0.3;
                mood = this.state.bond < 30 ? "lonely" : "sleepy";
            }

            this.state.energy = clamp(this.state.energy + delta.energy);
            this.state.happiness = clamp(this.state.happiness + delta.happiness);
            this.state.bond = clamp(this.state.bond + delta.bond);
            this.state.mood = MOODS[mood] ? mood : PETS[this.petId].defaultMood;
            this.state.moodChangedAt = Date.now();
            this.lastActionAt = Date.now();
            this.memory.lastSeenAt = this.lastActionAt;
            this.memory.lastSeenDate = dayKey(new Date(this.lastActionAt));
            let line = detail.line || (event === "streak-broken" ? PETS[this.petId].resetLine : undefined);
            if (event === "user-return" && detail.daysAway) line = PETS[this.petId].returnLine(detail.daysAway);
            this.save();
            this.onChange(this.snapshot({ event, line, previousMood, announce: event !== "activity", detail }));
        }

        tick() {
            const now = Date.now();
            const minutes = Math.max(0, (now - this.lastTickAt) / 60000);
            this.lastTickAt = now;
            if (!minutes) return;

            const idleMinutes = (now - this.lastActionAt) / 60000;
            this.state.energy = clamp(this.state.energy - minutes * (idleMinutes > 20 ? 0.28 : 0.07));
            this.state.happiness = clamp(this.state.happiness - minutes * 0.025);
            if (idleMinutes > 15) this.state.bond = clamp(this.state.bond - minutes * 0.035);

            let nextMood = this.state.mood;
            if (idleMinutes >= 180 && this.state.bond < 20) nextMood = "sad";
            else if (idleMinutes >= 45 && this.state.bond < 32) nextMood = "lonely";
            else if (idleMinutes >= 14 || this.state.energy < 28) nextMood = "sleepy";
            else if (this.state.moodChangedAt + 120000 < now) nextMood = PETS[this.petId].defaultMood;

            if (nextMood !== this.state.mood) {
                const previousMood = this.state.mood;
                this.state.mood = nextMood;
                this.state.moodChangedAt = now;
                const line = nextMood === "lonely" || nextMood === "sad" ? PETS[this.petId].lines[nextMood] : nextMood === "sleepy" ? PETS[this.petId].lines.sleepy : "";
                this.save();
                this.onChange(this.snapshot({ event: "idle", previousMood, line, announce: Boolean(line) }));
            } else {
                this.save();
            }
        }

        snapshot(extra = {}) {
            const trait = MOODS[this.state.mood] || MOODS[PETS[this.petId].defaultMood];
            return {
                petId: this.petId,
                name: window.StashCompanions?.get(this.petId)?.name || this.petId,
                mood: this.state.mood,
                face: trait.face,
                animation: trait.animation,
                glow: trait.glow,
                soundHz: trait.soundHz,
                line: extra.line || PETS[this.petId].lines[this.state.mood],
                energy: Math.round(this.state.energy),
                happiness: Math.round(this.state.happiness),
                bond: Math.round(this.state.bond),
                streak: Number(this.memory.streak) || 0,
                ...extra,
            };
        }

        savePetState() {
            if (!this.memory.pets || typeof this.memory.pets !== "object") this.memory.pets = {};
            this.memory.pets[this.petId] = { ...this.state };
        }

        save() {
            this.savePetState();
            try {
                localStorage.setItem(STORAGE_KEY, JSON.stringify(this.memory));
            } catch {
                // The current page still keeps its mood if storage is unavailable.
            }
        }
    }

    window.Pet5MoodEngine = { Pet5MoodEngine, PETS, MOODS };
})();
/* END PETS-5 */
