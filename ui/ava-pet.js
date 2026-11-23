"use strict";

(() => {
    const app = document.getElementById("app");
    const widget = document.getElementById("avaPetWidget");
    const button = document.getElementById("avaPetButton");
    const bubble = document.getElementById("avaPetBubble");
    const shortcutButton = document.getElementById("avaPetShortcutButton");
    const shortcutStatus = document.getElementById("avaPetShortcutStatus");
    const petChoice = document.getElementById("avaPetChoice");
    const petVoiceStyle = document.getElementById("avaPetVoiceStyle");
    const petMicButton = document.getElementById("avaPetMicButton");
    const petName = widget.querySelector(".ava-pet-name");
    if (!app || !widget || !button || !bubble) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const shortcutStorageKey = "stashAvaShortcutV1";
    const petStorageKey = "stashAvaPetChoiceV1";
    const voiceStorageKey = "stashAvaVoiceStyleV1";
    const companionConfig = window.StashCompanions;
    const pets = Object.fromEntries((companionConfig?.legacyChoices || []).map(item => [item.legacyId, item.name]));
    const width = () => window.matchMedia("(max-width: 650px)").matches ? 68 : 82;
    const height = () => window.matchMedia("(max-width: 650px)").matches ? 82 : 96;
    let x = 0;
    let y = 0;
    let targetX = 0;
    let targetY = 0;
    let animationFrame = 0;
    let bubbleTimer = 0;
    let actionTimer = 0;
    let expressionTimer = 0;
    let currentMood = "curious";
    let storageMood = "curious";
    let lastStorageMood = "";
    let userVisible = false;
    let capturingShortcut = false;
    let shortcut = loadShortcut();
    let selectedPet = loadChoice(petStorageKey, Object.keys(pets), "ava");
    let selectedVoice = loadChoice(voiceStorageKey, ["natural", "cartoon", "off"], "cartoon");

    const sillyMessages = [
        "Boop. I’m on tiny copy patrol.",
        "Important robot business: one little wiggle.",
        "I have three pixels of confidence and zero fear.",
        "Your copies are safe. My dance moves are questionable.",
        "I’m the tiniest file detective in Stash.",
    ];

    function loadShortcut() {
        try {
            const saved = JSON.parse(localStorage.getItem(shortcutStorageKey) || "null");
            if (
                saved && ["alt", "ctrl", "meta"].includes(saved.modifier)
                && /^[a-z0-9]$/i.test(saved.key || "")
            ) {
                return { modifier: saved.modifier, key: saved.key.toLowerCase() };
            }
        } catch {
            // Use the default if the browser cannot read the saved setting.
        }
        return { modifier: "alt", key: "a" };
    }

    function loadChoice(key, choices, fallback) {
        try {
            const value = localStorage.getItem(key);
            if (choices.includes(value)) return value;
        } catch {
            // Use the default if this browser blocks local storage.
        }
        return fallback;
    }

    function setPetChoice(value, persist = true) {
        selectedPet = pets[value] ? value : "ava";
        widget.dataset.pet = selectedPet;
        const name = pets[selectedPet];
        if (petName) petName.textContent = name;
        button.setAttribute("aria-label", `${name}, your Stash companion. Click for a message.`);
        button.title = `${name} the Stash companion`;
        widget.setAttribute("aria-label", `${name} companion`);
        if (petChoice) {
            const selected = companionConfig?.legacyChoices.find(item => item.legacyId === selectedPet);
            petChoice.value = selected?.id || selectedPet;
        }
        if (persist) {
            try { localStorage.setItem(petStorageKey, selectedPet); } catch { /* page-only preference */ }
        }
    }

    function setVoiceChoice(value, persist = true) {
        selectedVoice = ["natural", "cartoon", "off"].includes(value) ? value : "cartoon";
        if (petVoiceStyle) petVoiceStyle.value = selectedVoice;
        if (persist) {
            try { localStorage.setItem(voiceStorageKey, selectedVoice); } catch { /* page-only preference */ }
        }
    }

    function formatShortcut(value = shortcut) {
        const modifierLabels = { alt: "Option", ctrl: "Control", meta: "Command" };
        const modifierLabel = modifierLabels[value.modifier] || "Option";
        return `${modifierLabel} + ${String(value.key || "a").toUpperCase()}`;
    }

    function updateShortcutSetting(message = "") {
        if (shortcutStatus) shortcutStatus.textContent = message || formatShortcut();
        if (shortcutButton) shortcutButton.textContent = capturingShortcut ? "Cancel" : "Change shortcut";
    }

    function clampPosition(nextX, nextY) {
        const maxX = Math.max(8, window.innerWidth - width() - 8);
        const maxY = Math.max(8, window.innerHeight - height() - 8);
        return {
            x: Math.max(8, Math.min(maxX, nextX)),
            y: Math.max(8, Math.min(maxY, nextY)),
        };
    }

    function cornerPosition() {
        return clampPosition(window.innerWidth - width() - 18, window.innerHeight - height() - 18);
    }

    function animateToTarget() {
        x += (targetX - x) * (reducedMotion.matches ? 1 : 0.2);
        y += (targetY - y) * (reducedMotion.matches ? 1 : 0.2);
        widget.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`;

        if (Math.abs(targetX - x) > 0.5 || Math.abs(targetY - y) > 0.5) {
            animationFrame = window.requestAnimationFrame(animateToTarget);
        } else {
            x = targetX;
            y = targetY;
            animationFrame = 0;
        }
    }

    function moveTo(nextX, nextY) {
        const point = clampPosition(nextX, nextY);
        targetX = point.x;
        targetY = point.y;
        if (!animationFrame) animationFrame = window.requestAnimationFrame(animateToTarget);
    }

    function applyVisibility() {
        const shouldHide = !userVisible;
        if (widget.hidden !== shouldHide) widget.hidden = shouldHide;
    }

    function speakPetMessage(message) {
        if (!message || selectedVoice === "off" || !("speechSynthesis" in window)
            || typeof SpeechSynthesisUtterance === "undefined") return;
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(message);
        utterance.lang = navigator.language || "en-US";
        if (selectedVoice === "cartoon") {
            utterance.pitch = 1.45;
            utterance.rate = 1.06;
        } else {
            utterance.pitch = 1;
            utterance.rate = 1;
        }
        window.speechSynthesis.speak(utterance);
    }

    function showMessage(message, duration = 4200, { speak = false } = {}) {
        window.clearTimeout(bubbleTimer);
        bubble.textContent = message;
        bubble.hidden = false;
        if (speak) speakPetMessage(message);
        bubbleTimer = window.setTimeout(() => {
            bubble.hidden = true;
        }, duration);
    }

    function setMood(mood) {
        currentMood = mood;
        widget.dataset.mood = mood;
    }

    function performAction(action, preserveMood = false) {
        widget.classList.remove("is-waving", "is-hopping", "is-dancing", "is-peeking");
        void widget.offsetWidth;
        widget.classList.add(`is-${action}`);
        if (!preserveMood && storageMood !== "sad" && storageMood !== "worried") {
            window.clearTimeout(expressionTimer);
            setMood(action === "peeking" ? "curious" : "happy");
            expressionTimer = window.setTimeout(() => setMood(storageMood), 1800);
        }
        window.setTimeout(() => widget.classList.remove(`is-${action}`), 1500);
    }

    function scheduleIdleAction() {
        window.clearTimeout(actionTimer);
        actionTimer = window.setTimeout(() => {
            if (!widget.hidden) {
                const actions = ["waving", "hopping", "dancing", "peeking"];
                performAction(actions[Math.floor(Math.random() * actions.length)]);
                if (Math.random() < 0.3) {
                    showMessage(sillyMessages[Math.floor(Math.random() * sillyMessages.length)]);
                }
            }
            scheduleIdleAction();
        }, 18000 + Math.random() * 18000);
    }

    function react({ mood = "curious", message = "", action = "peeking", duration = 5200, modal = false, speak = false } = {}) {
        const vaultDialog = modal ? document.getElementById("vaultDialog") : null;
        if (!widget.hidden && vaultDialog?.open) {
            vaultDialog.appendChild(widget);
            const bounds = vaultDialog.getBoundingClientRect();
            moveTo(bounds.right - width() - 14, bounds.top + 14);
        } else if (!widget.hidden) {
            if (widget.parentElement !== app) app.appendChild(widget);
            const point = cornerPosition();
            moveTo(point.x, point.y);
        }
        window.clearTimeout(expressionTimer);
        setMood(mood);
        if (!widget.hidden && message) showMessage(message, duration, { speak });
        if (!widget.hidden && ["waving", "hopping", "dancing", "peeking"].includes(action)) performAction(action, true);
        if (!widget.hidden) expressionTimer = window.setTimeout(() => setMood(storageMood), duration);
    }

    function reportStorage({ ready, percent } = {}) {
        if (!ready) {
            storageMood = "curious";
            window.clearTimeout(expressionTimer);
            setMood("curious");
            lastStorageMood = "unavailable";
            return;
        }

        const nextMood = percent >= 100 ? "sad" : percent >= 90 ? "worried" : percent >= 70 ? "concerned" : percent <= 15 ? "happy" : "calm";
        if (nextMood === lastStorageMood) return;
        const previousMood = lastStorageMood;
        lastStorageMood = nextMood;
        storageMood = nextMood;
        window.clearTimeout(expressionTimer);
        setMood(nextMood);

        if (nextMood === "sad") {
            react({ mood: "sad", message: "Cloud storage is full! I vote for a tiny cleanup break.", action: "peeking", duration: 6500, speak: true });
        } else if (nextMood === "worried") {
            react({ mood: "worried", message: "Cloud space is getting tight. Maybe peek at Settings → Cloud storage.", action: "peeking", duration: 6000, speak: true });
        } else if (previousMood === "sad" || previousMood === "worried") {
            react({ mood: "happy", message: "Phew! There’s a little more room to breathe.", action: "hopping", duration: 5000, speak: true });
        } else if (nextMood === "happy") {
            react({ mood: "happy", message: "Plenty of room. I can relax my tiny robot shoulders.", action: "hopping", duration: 4500, speak: true });
        }
    }

    function toggleVisibility() {
        userVisible = !userVisible;
        applyVisibility();
        if (userVisible) {
            const point = cornerPosition();
            moveTo(point.x, point.y);
            setMood(storageMood);
            showMessage(storageMood === "sad"
                ? "I’m a little blue. A bit of cloud space would cheer me up!"
                : "I’m here. No cursor chasing, promise.", 4200, { speak: true });
            performAction("waving");
        } else {
            window.clearTimeout(bubbleTimer);
            bubble.hidden = true;
        }
    }

    function stopShortcutCapture() {
        capturingShortcut = false;
        updateShortcutSetting();
    }

    shortcutButton?.addEventListener("click", () => {
        if (capturingShortcut) {
            stopShortcutCapture();
            return;
        }
        capturingShortcut = true;
        updateShortcutSetting("Press Option, Control, or Command + one letter or number");
    });

    document.addEventListener("keydown", event => {
        if (!capturingShortcut) return;
        if (capturingShortcut) {
            if (event.key === "Escape") {
                event.preventDefault();
                stopShortcutCapture();
                return;
            }
            const key = event.code?.startsWith("Key")
                ? event.code.slice(3).toLowerCase()
                : event.code?.startsWith("Digit")
                    ? event.code.slice(5)
                    : "";
            if (event.repeat || event.isComposing || !/^[a-z0-9]$/i.test(key)) return;
            const modifiers = [event.altKey && "alt", event.ctrlKey && "ctrl", event.metaKey && "meta"].filter(Boolean);
            if (modifiers.length !== 1 || event.shiftKey) {
                updateShortcutSetting("Use exactly one modifier plus a letter or number");
                return;
            }
            event.preventDefault();
            shortcut = { modifier: modifiers[0], key };
            try {
                localStorage.setItem(shortcutStorageKey, JSON.stringify(shortcut));
            } catch {
                // The shortcut still works for this page if storage is unavailable.
            }
            stopShortcutCapture();
            return;
        }
    });

    function setChoiceFromRegistry(id) {
        const companion = companionConfig?.get(id);
        if (companion?.kind === "legacy") setPetChoice(companion.legacyId);
    }

    function showFromController(id) {
        setChoiceFromRegistry(id);
        if (!userVisible) {
            userVisible = true;
            applyVisibility();
            const point = cornerPosition();
            moveTo(point.x, point.y);
            setMood(storageMood);
            showMessage("I’m here. No cursor chasing, promise.", 4200, { speak: false });
            performAction("waving");
        }
    }

    function hideFromController() {
        userVisible = false;
        window.clearTimeout(bubbleTimer);
        bubble.hidden = true;
        applyVisibility();
    }

    window.StashLegacyCompanion = Object.freeze({
        show: showFromController,
        hide: hideFromController,
        setChoice: setChoiceFromRegistry,
        toggle() { toggleVisibility(); },
    });

    button.addEventListener("click", () => {
        const message = currentMood === "sad"
            ? "I’m a little blue. A bit of cloud space would cheer me up!"
            : currentMood === "worried"
                ? "Storage is nearly full. I’ll keep watch while you check Settings."
                : sillyMessages[Math.floor(Math.random() * sillyMessages.length)];
        showMessage(message, 4200, { speak: true });
        performAction(["waving", "hopping", "dancing"][Math.floor(Math.random() * 3)]);
    });

    petVoiceStyle?.addEventListener("change", () => setVoiceChoice(petVoiceStyle.value));
    petMicButton?.addEventListener("click", () => {
        window.dispatchEvent(new CustomEvent("stash:voice-input-request"));
    });

    window.addEventListener("stash:ava-voice-listening", () => {
        react({ mood: "listening", message: "I’m listening…", action: "peeking", duration: 30000 });
    });
    window.addEventListener("stash:ava-voice-error", event => {
        react({ mood: "confused", message: event.detail?.message || "I missed that. Try me again?", action: "peeking", duration: 5000, speak: true });
    });
    window.addEventListener("stash:ava-voice-response", () => {
        react({ mood: "excited", action: "hopping", duration: 2600 });
    });

    window.addEventListener("stash:storage-usage", event => reportStorage(event.detail || {}));
    window.addEventListener("stash:ava-reaction", event => react(event.detail || {}));
    window.addEventListener("stash:ava-return-home", () => {
        app.appendChild(widget);
        if (!widget.hidden) {
            const point = cornerPosition();
            moveTo(point.x, point.y);
        }
    });
    document.addEventListener("copy-maker:workspace-ready", () => {
        window.setTimeout(() => {
            if (!app.hidden && userVisible) performAction("waving");
        }, 700);
    });
    window.addEventListener("resize", () => {
        if (widget.hidden) return;
        const point = cornerPosition();
        moveTo(point.x, point.y);
    });
    reducedMotion.addEventListener?.("change", () => {
        if (reducedMotion.matches && animationFrame) {
            window.cancelAnimationFrame(animationFrame);
            animationFrame = 0;
            x = targetX;
            y = targetY;
            widget.style.transform = `translate3d(${x}px, ${y}px, 0)`;
        }
    });

    widget.hidden = true;
    setPetChoice(selectedPet, false);
    setVoiceChoice(selectedVoice, false);
    const initialPoint = cornerPosition();
    x = targetX = initialPoint.x;
    y = targetY = initialPoint.y;
    widget.style.transform = `translate3d(${x}px, ${y}px, 0)`;
    updateShortcutSetting();
    scheduleIdleAction();
})();
