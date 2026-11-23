/* PETS-5: additive picker, floating companion stage, and interaction adapter. */
(() => {
    "use strict";

    const app = document.getElementById("app");
    const root = document.getElementById("pet5Root");
    const stage = document.getElementById("pet5Stage");
    const companion = document.getElementById("pet5Companion");
    const artHost = document.getElementById("pet5ArtHost");
    const nameLabel = document.getElementById("pet5Name");
    const bubble = document.getElementById("pet5Bubble");
    const meterStatus = document.getElementById("pet5MeterStatus");
    const pickerButton = document.getElementById("pet5PickerButton");
    const pickerCurrent = document.getElementById("pet5PickerCurrent");
    const pickerMenu = document.getElementById("pet5PickerMenu");
    const muteButton = document.getElementById("pet5MuteButton");
    const hideButton = document.getElementById("pet5HideButton");
    const legacyWidget = document.getElementById("avaPetWidget");
    const legacyVoice = document.getElementById("avaPetVoiceStyle");
    const petChoice = document.getElementById("avaPetChoice");
    const companionConfig = window.StashCompanions;
    const engineApi = window.Pet5MoodEngine;
    const componentApi = window.Pet5Components;
    if (!app || !root || !stage || !companion || !artHost || !engineApi || !componentApi || !companionConfig) return;

    const { Pet5MoodEngine, PETS } = engineApi;
    const { COMPONENTS } = componentApi;
    const KEYS = {
        active: "copyMakerPet5ActiveV1",
        hidden: "copyMakerPet5HiddenV1",
        muted: "copyMakerPet5MutedV1",
        sound: "copyMakerPet5SoundV1",
        legacyVoice: "copyMakerPet5LegacyVoiceV1",
        position: "copyMakerPet5PositionV1",
    };
    const safeRead = key => {
        try { return localStorage.getItem(key); } catch { return null; }
    };
    const safeWrite = (key, value) => {
        try { localStorage.setItem(key, value); } catch { /* Page-only preference if storage is unavailable. */ }
    };
    const safeRemove = key => {
        try { localStorage.removeItem(key); } catch { /* Page-only preference if storage is unavailable. */ }
    };
    const cssValue = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const cssMs = name => {
        const value = cssValue(name);
        const parsed = Number.parseFloat(value) || 0;
        return value.endsWith("s") && !value.endsWith("ms") ? parsed * 1000 : parsed;
    };
    const cssPx = name => Number.parseFloat(cssValue(name)) || 0;
    const readBool = (key, fallback) => {
        const value = safeRead(key);
        return value === null ? fallback : value === "true";
    };
    const registryIds = new Set(companionConfig.all.map(item => item.id));
    const legacyChoiceId = value => {
        const legacyId = value === "mochi" ? "mochi" : value;
        return companionConfig.legacyChoices.find(item => item.legacyId === legacyId)?.id || "ava";
    };
    let storedPet = safeRead(KEYS.active);
    if (storedPet === "legacy") storedPet = legacyChoiceId(safeRead("stashAvaPetChoiceV1"));
    if (!storedPet) storedPet = legacyChoiceId(safeRead("stashAvaPetChoiceV1"));
    let activePet = registryIds.has(storedPet) ? storedPet : "ava";
    const petNames = Object.fromEntries(companionConfig.all.map(item => [item.id, item.name]));
    let allHidden = readBool(KEYS.hidden, false);
    let allMuted = readBool(KEYS.muted, false);
    let soundEnabled = readBool(KEYS.sound, false) && !allMuted;
    let companionVisible = false;
    let bubbleTimer = 0;
    let blinkTimer = 0;
    let tickTimer = 0;
    let timeCheckTimer = 0;
    let focusStartedAt = 0;
    let focusMoodSent = false;
    let lastRapidTypingAt = 0;
    let lastErrorAt = 0;
    let hiddenAt = 0;
    let audioContext = null;
    let pointerFrame = 0;
    let transitionTimer = 0;
    let lastPointerPoint = null;
    let tapTimer = 0;
    let lastTapAt = 0;
    let recentPetTaps = 0;
    let firstRecentPetTapAt = 0;
    let pointerState = null;
    let savedPosition = null;
    let libraryObserver = null;
    const seenCopyIds = new Set();
    const typingTimes = [];

    const isLegacyActive = () => companionConfig.get(activePet)?.kind === "legacy";

    function buildCompanionSelectors() {
        if (petChoice) {
            petChoice.replaceChildren();
            for (const item of companionConfig.all) {
                const option = document.createElement("option");
                option.value = item.id;
                option.textContent = `${item.name} · ${item.description}`;
                petChoice.append(option);
            }
            petChoice.value = activePet;
        }
        pickerMenu.replaceChildren();
        for (const item of companionConfig.all) {
            const button = document.createElement("button");
            button.className = "pet5-picker-item";
            button.type = "button";
            button.dataset.pet5Choice = item.id;
            button.setAttribute("aria-pressed", String(item.id === activePet));
            button.append(document.createTextNode(item.name));
            const description = document.createElement("span");
            description.textContent = item.description;
            button.append(description);
            pickerMenu.append(button);
        }
    }

    buildCompanionSelectors();

    const initialPosition = (() => {
        try { return JSON.parse(safeRead(KEYS.position) || "null"); } catch { return null; }
    })();

    function showBubble(message) {
        if (!bubble || !message) return;
        window.clearTimeout(bubbleTimer);
        bubble.textContent = message;
        bubble.hidden = false;
        bubbleTimer = window.setTimeout(() => { bubble.hidden = true; }, cssMs("--pet5-speech-duration"));
    }

    function playSound(snapshot) {
        if (allMuted || !soundEnabled || !snapshot?.soundHz) return;
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) return;
        try {
            audioContext ||= new AudioContextClass();
            if (audioContext.state === "suspended") audioContext.resume();
            const oscillator = audioContext.createOscillator();
            const gain = audioContext.createGain();
            const now = audioContext.currentTime;
            oscillator.type = "sine";
            oscillator.frequency.setValueAtTime(snapshot.soundHz, now);
            gain.gain.setValueAtTime(0.0001, now);
            gain.gain.exponentialRampToValueAtTime(0.035, now + 0.012);
            gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.105);
            oscillator.connect(gain);
            gain.connect(audioContext.destination);
            oscillator.start(now);
            oscillator.stop(now + 0.11);
        } catch {
            // Companion sound stays optional when Web Audio is unavailable.
        }
    }

    function renderSnapshot(snapshot) {
        if (!snapshot || isLegacyActive()) return;
        stage.dataset.pet = snapshot.petId;
        stage.dataset.mood = snapshot.mood;
        stage.dataset.face = snapshot.face;
        stage.dataset.animation = snapshot.animation;
        stage.dataset.glow = snapshot.glow;
        stage.classList.remove("pet5-transition");
        window.clearTimeout(transitionTimer);
        window.requestAnimationFrame(() => {
            stage.classList.add("pet5-transition");
            transitionTimer = window.setTimeout(() => stage.classList.remove("pet5-transition"), cssMs("--pet5-transition-duration"));
        });
        companion.setAttribute("aria-label", `${snapshot.name}, ${snapshot.mood}. Energy ${snapshot.energy} percent, happiness ${snapshot.happiness} percent, bond ${snapshot.bond} percent. Tap to pet, drag to move, long-press to chat, or double-tap for a trick.`);
        if (meterStatus) meterStatus.textContent = `${snapshot.name}: ${snapshot.mood}; energy ${snapshot.energy} percent; happiness ${snapshot.happiness} percent; bond ${snapshot.bond} percent; streak ${snapshot.streak} days.`;
        if (snapshot.announce && snapshot.line && !allHidden && !app.hidden) showBubble(snapshot.line);
        if (snapshot.event && snapshot.event !== "start" && snapshot.event !== "switch") playSound(snapshot);
        updateControls();
    }

    const engine = new Pet5MoodEngine(isLegacyActive() ? "orbi" : activePet, renderSnapshot);
    let engineInitialized = false;

    function initializeEngine() {
        if (engineInitialized || app.hidden) return;
        engineInitialized = true;
        engine.initialize();
    }

    function updateControls() {
        if (pickerCurrent) pickerCurrent.textContent = petNames[activePet] || "Orbi";
        if (petChoice) petChoice.value = activePet;
        if (pickerButton) pickerButton.setAttribute("aria-expanded", String(!pickerMenu.hidden));
        pickerMenu.querySelectorAll("[data-pet5-choice]").forEach(button => {
            button.setAttribute("aria-pressed", String(button.dataset.pet5Choice === activePet));
        });
        if (muteButton) {
            muteButton.textContent = allMuted ? "Muted" : "Mute";
            muteButton.setAttribute("aria-pressed", String(allMuted));
            muteButton.setAttribute("aria-label", allMuted ? "Turn all pet sounds on" : "Mute all pets");
            muteButton.title = allMuted ? "Turn all pet sounds on" : "Mute all pets";
        }
        if (hideButton) {
            hideButton.textContent = allHidden ? "Show" : "Hide";
            hideButton.setAttribute("aria-pressed", String(allHidden));
            hideButton.setAttribute("aria-label", allHidden ? "Show the selected pet" : "Hide all pets");
        }
    }

    function closeMenu() {
        pickerMenu.hidden = true;
        pickerButton.setAttribute("aria-expanded", "false");
    }

    function renderPet(petId) {
        const component = COMPONENTS[petId];
        if (!component) return;
        artHost.innerHTML = component.render();
        stage.dataset.pet = petId;
        stage.dataset.trick = "";
        if (nameLabel) nameLabel.textContent = petNames[petId];
        companion.setAttribute("aria-label", `${petNames[petId]}, your companion. Tap to pet, drag to move, long-press to chat, or double-tap for a trick.`);
    }

    function updateVisibility() {
        const appReady = !app.hidden;
        const showCompanion = appReady && companionVisible && !allHidden;
        root.hidden = !appReady || !companionVisible;
        stage.hidden = !showCompanion || isLegacyActive();
        document.body.classList.toggle("pet5-exclusive", !isLegacyActive());
        document.body.classList.toggle("pet5-hidden-all", allHidden);
        if (allHidden || !companionVisible) {
            bubble.hidden = true;
            window.clearTimeout(bubbleTimer);
        }
        if (isLegacyActive()) {
            if (showCompanion) window.StashLegacyCompanion?.show(activePet);
            else window.StashLegacyCompanion?.hide();
        } else {
            window.StashLegacyCompanion?.hide();
        }
        updateControls();
        if (!stage.hidden) scheduleBlink();
        else window.clearTimeout(blinkTimer);
    }

    function setActivePet(petId) {
        const selection = companionConfig.get(petId);
        if (!selection) return;
        activePet = petId;
        safeWrite(KEYS.active, petId);
        closeMenu();
        if (petChoice) petChoice.value = petId;
        setLegacyVoiceMuted(allMuted || !isLegacyActive());
        if (isLegacyActive()) {
            window.StashLegacyCompanion?.setChoice(petId);
        } else {
            renderPet(petId);
            engine.setPet(petId);
        }
        updateVisibility();
    }

    function setLegacyVoiceMuted(muted) {
        if (!legacyVoice) return;
        if (muted) {
            if (safeRead(KEYS.legacyVoice) === null) safeWrite(KEYS.legacyVoice, legacyVoice.value);
            if (legacyVoice.value !== "off") {
                legacyVoice.value = "off";
                legacyVoice.dispatchEvent(new Event("change", { bubbles: true }));
            }
            return;
        }
        const savedVoice = safeRead(KEYS.legacyVoice);
        if (savedVoice && ["natural", "cartoon", "off"].includes(savedVoice)) {
            legacyVoice.value = savedVoice;
            legacyVoice.dispatchEvent(new Event("change", { bubbles: true }));
        }
        safeRemove(KEYS.legacyVoice);
    }

    function setAllMuted(nextMuted) {
        allMuted = Boolean(nextMuted);
        soundEnabled = !allMuted;
        safeWrite(KEYS.muted, String(allMuted));
        safeWrite(KEYS.sound, String(soundEnabled));
        setLegacyVoiceMuted(allMuted || !isLegacyActive());
        if (!allMuted) playSound(engine.snapshot({ event: "unmute" }));
        updateControls();
    }

    function setAllHidden(nextHidden) {
        allHidden = Boolean(nextHidden);
        safeWrite(KEYS.hidden, String(allHidden));
        updateVisibility();
    }

    function shortcutMatches(event) {
        let shortcut = { modifier: "alt", key: "a" };
        try {
            const saved = JSON.parse(safeRead("stashAvaShortcutV1") || "null");
            if (saved && ["alt", "ctrl", "meta"].includes(saved.modifier) && /^[a-z0-9]$/i.test(saved.key || "")) shortcut = saved;
        } catch {
            // The default Option + A shortcut remains available if preferences cannot be read.
        }
        const key = event.code?.startsWith("Key")
            ? event.code.slice(3).toLowerCase()
            : event.code?.startsWith("Digit")
                ? event.code.slice(5)
                : "";
        return key === shortcut.key.toLowerCase()
            && event.altKey === (shortcut.modifier === "alt")
            && event.ctrlKey === (shortcut.modifier === "ctrl")
            && event.metaKey === (shortcut.modifier === "meta")
            && !event.shiftKey;
    }

    function isTextEntry(target) {
        return Boolean(target?.closest?.("input, textarea, select, [contenteditable='true']"));
    }

    function toggleCompanion() {
        if (companionVisible) {
            companionVisible = false;
        } else {
            companionVisible = true;
            if (allHidden) {
                allHidden = false;
                safeWrite(KEYS.hidden, "false");
            }
        }
        updateVisibility();
    }

    function trigger(event, detail = {}) {
        if (isLegacyActive()) return;
        engine.trigger(event, detail);
    }

    function scheduleBlink() {
        window.clearTimeout(blinkTimer);
        if (stage.hidden || document.hidden) return;
        const min = cssMs("--pet5-blink-min");
        const max = cssMs("--pet5-blink-max");
        blinkTimer = window.setTimeout(() => {
            stage.classList.add("pet5-blinking");
            window.setTimeout(() => stage.classList.remove("pet5-blinking"), cssMs("--pet5-blink-duration"));
            scheduleBlink();
        }, min + Math.random() * Math.max(0, max - min));
    }

    function playTrick() {
        const component = COMPONENTS[activePet];
        if (!component) return;
        stage.dataset.trick = component.trickName;
        window.clearTimeout(stage._pet5TrickTimer);
        stage._pet5TrickTimer = window.setTimeout(() => { stage.dataset.trick = ""; }, cssMs("--pet5-trick-duration"));
        trigger("double-tap", { line: component.trick });
    }

    function handleTap() {
        const now = Date.now();
        const doubleTapMs = cssMs("--pet5-double-tap");
        if (lastTapAt && now - lastTapAt <= doubleTapMs) {
            window.clearTimeout(tapTimer);
            lastTapAt = 0;
            playTrick();
            return;
        }
        lastTapAt = now;
        window.clearTimeout(tapTimer);
        tapTimer = window.setTimeout(() => {
            lastTapAt = 0;
            if (firstRecentPetTapAt && now - firstRecentPetTapAt > cssMs("--pet5-rapid-pet-window")) recentPetTaps = 0;
            if (!recentPetTaps) firstRecentPetTapAt = Date.now();
            recentPetTaps += 1;
            if (recentPetTaps >= 5) {
                recentPetTaps = 0;
                firstRecentPetTapAt = 0;
                trigger("pet-too-many", { line: PETS[activePet].lines["angry-cute"] });
            } else {
                trigger("pet");
            }
        }, doubleTapMs);
    }

    function clampPoint(x, y) {
        const bounds = stage.getBoundingClientRect();
        const width = bounds.width || cssPx("--pet5-size");
        const height = bounds.height || cssPx("--pet5-size") + cssPx("--pet5-name-height");
        return {
            x: Math.max(cssPx("--pet5-space-2"), Math.min(window.innerWidth - width - cssPx("--pet5-space-2"), x)),
            y: Math.max(cssPx("--pet5-space-2"), Math.min(window.innerHeight - height - cssPx("--pet5-space-2"), y)),
        };
    }

    function rememberPosition() {
        const bounds = stage.getBoundingClientRect();
        savedPosition = { x: Math.round(bounds.left), y: Math.round(bounds.top) };
        safeWrite(KEYS.position, JSON.stringify(savedPosition));
    }

    function restorePosition() {
        if (!savedPosition || !Number.isFinite(savedPosition.x) || !Number.isFinite(savedPosition.y)) return;
        const point = clampPoint(savedPosition.x, savedPosition.y);
        stage.style.left = `${point.x}px`;
        stage.style.top = `${point.y}px`;
        stage.style.right = "auto";
        stage.style.bottom = "auto";
    }

    function beginDrag(event) {
        if (event.button !== undefined && event.button !== 0) return;
        pointerState = { id: event.pointerId, x: event.clientX, y: event.clientY, startX: event.clientX, startY: event.clientY, dragging: false, long: false };
        window.clearTimeout(pointerState.longTimer);
        pointerState.longTimer = window.setTimeout(() => {
            if (!pointerState || pointerState.dragging) return;
            pointerState.long = true;
            trigger("long-press", { line: `${petNames[activePet]} is here for a tiny chat. ${PETS[activePet]?.lines?.curious || "What’s on your mind?"}` });
        }, cssMs("--pet5-long-press"));
        try { companion.setPointerCapture(event.pointerId); } catch { /* Pointer capture is optional. */ }
    }

    function moveDrag(event) {
        if (!pointerState || event.pointerId !== pointerState.id) return;
        const deltaX = event.clientX - pointerState.startX;
        const deltaY = event.clientY - pointerState.startY;
        if (!pointerState.dragging && Math.hypot(deltaX, deltaY) > cssPx("--pet5-drag-threshold")) {
            pointerState.dragging = true;
            window.clearTimeout(pointerState.longTimer);
            const bounds = stage.getBoundingClientRect();
            stage.style.left = `${bounds.left}px`;
            stage.style.top = `${bounds.top}px`;
            stage.style.right = "auto";
            stage.style.bottom = "auto";
            stage.classList.add("pet5-picked-up");
            trigger("drag-start");
        }
        if (pointerState.dragging) {
            const point = clampPoint(event.clientX - (companion.getBoundingClientRect().width / 2), event.clientY - (companion.getBoundingClientRect().height / 2));
            stage.style.left = `${point.x}px`;
            stage.style.top = `${point.y}px`;
        }
    }

    function endDrag(event) {
        if (!pointerState || event.pointerId !== pointerState.id) return;
        const pointer = pointerState;
        pointerState = null;
        window.clearTimeout(pointer.longTimer);
        if (pointer.dragging) {
            stage.classList.remove("pet5-picked-up");
            rememberPosition();
            trigger("drag-drop");
        } else if (!pointer.long) {
            handleTap();
        }
    }

    function trackEyes(event) {
        if (stage.hidden || isLegacyActive()) return;
        lastPointerPoint = { x: event.clientX, y: event.clientY };
        if (pointerFrame) return;
        pointerFrame = window.requestAnimationFrame(() => {
            pointerFrame = 0;
            if (!lastPointerPoint) return;
            const bounds = companion.getBoundingClientRect();
            const x = Math.max(-2, Math.min(2, (lastPointerPoint.x - (bounds.left + bounds.width / 2)) / 36));
            const y = Math.max(-1.5, Math.min(1.5, (lastPointerPoint.y - (bounds.top + bounds.height / 2)) / 48));
            root.style.setProperty("--pet5-eye-x", `${x}px`);
            root.style.setProperty("--pet5-eye-y", `${y}px`);
        });
    }

    function getRowKey(row) {
        return String(row._copyMakerItem?.id ?? row.dataset.copyId ?? row.querySelector(".copy-title")?.textContent ?? "").trim();
    }

    function registerNewRows(node, suppress = false) {
        if (!(node instanceof Element)) return;
        const rows = [];
        if (node.matches(".copy-row")) rows.push(node);
        rows.push(...node.querySelectorAll(".copy-row"));
        for (const row of rows) {
            const key = getRowKey(row);
            if (!key || seenCopyIds.has(key)) continue;
            seenCopyIds.add(key);
            if (!suppress && !row.classList.contains("copy-row-pending")) trigger("task-complete");
        }
    }

    function attachTaskObserver() {
        const list = document.querySelector(".library-content");
        if (!list || libraryObserver) return;
        list.querySelectorAll(".copy-row").forEach(row => { const key = getRowKey(row); if (key) seenCopyIds.add(key); });
        let suppressUntil = Date.now() + cssMs("--pet5-initial-scan");
        libraryObserver = new MutationObserver(records => {
            const suppress = Date.now() < suppressUntil;
            for (const record of records) record.addedNodes.forEach(node => registerNewRows(node, suppress));
        });
        libraryObserver.observe(list, { childList: true, subtree: true });
        window.setTimeout(() => { suppressUntil = 0; }, cssMs("--pet5-initial-scan"));
    }

    function reportError() {
        if (isLegacyActive() || Date.now() - lastErrorAt < cssMs("--pet5-error-cooldown")) return;
        lastErrorAt = Date.now();
        trigger("task-error");
    }

    function inspectErrorNode(node) {
        if (!(node instanceof Element)) return;
        const candidates = [];
        const selector = '[role="alert"], [data-kind="error"], .settings-status, .provider-message, .auth-message';
        if (node.matches(selector)) candidates.push(node);
        candidates.push(...node.querySelectorAll(selector));
        for (const candidate of candidates) {
            if (/^\s*(?:error\b|could not\b|failed\b|unable to\b|something went wrong\b)/i.test(candidate.textContent || "")) {
                reportError();
                break;
            }
        }
    }

    function updateFocusSession() {
        if (isLegacyActive() || !focusStartedAt || focusMoodSent || Date.now() - focusStartedAt < cssMs("--pet5-long-focus")) return;
        focusMoodSent = true;
        trigger("focus-long");
    }

    /* PETS-5: picker selections are isolated from the legacy pet's settings and handlers. */
    pickerButton.addEventListener("click", () => {
        pickerMenu.hidden = !pickerMenu.hidden;
        pickerButton.setAttribute("aria-expanded", String(!pickerMenu.hidden));
    });
    pickerMenu.addEventListener("click", event => {
        const choice = event.target.closest("[data-pet5-choice]");
        if (choice) setActivePet(choice.dataset.pet5Choice);
    });
    petChoice?.addEventListener("change", () => setActivePet(petChoice.value));
    muteButton.addEventListener("click", () => setAllMuted(!allMuted));
    hideButton.addEventListener("click", () => setAllHidden(!allHidden));
    companion.addEventListener("pointerdown", beginDrag);
    companion.addEventListener("pointermove", moveDrag);
    companion.addEventListener("pointerup", endDrag);
    companion.addEventListener("pointercancel", endDrag);
    companion.addEventListener("lostpointercapture", event => {
        if (pointerState && pointerState.id === event.pointerId) endDrag(event);
    });
    companion.addEventListener("click", event => {
        if (event.detail === 0 && !isLegacyActive() && !allHidden) trigger("pet");
    });
    window.addEventListener("pointermove", trackEyes, { passive: true });
    window.addEventListener("resize", () => {
        if (stage.style.left) {
            const bounds = stage.getBoundingClientRect();
            const point = clampPoint(bounds.left, bounds.top);
            stage.style.left = `${point.x}px`;
            stage.style.top = `${point.y}px`;
            rememberPosition();
        }
    });
    document.addEventListener("click", event => {
        if (!root.contains(event.target)) closeMenu();
    });
    document.addEventListener("keydown", event => {
        if (event.defaultPrevented || event.repeat || event.isComposing || isTextEntry(event.target) || !shortcutMatches(event)) return;
        if (app.hidden || document.hidden) return;
        event.preventDefault();
        toggleCompanion();
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && !pickerMenu.hidden) closeMenu();
    });

    /* PETS-5: legacy voice uses its existing preference control and change handler. */
    legacyVoice?.addEventListener("change", () => {
        if ((!allMuted && isLegacyActive()) || legacyVoice.value === "off") return;
        safeWrite(KEYS.legacyVoice, legacyVoice.value);
        legacyVoice.value = "off";
        legacyVoice.dispatchEvent(new Event("change", { bubbles: true }));
    });

    /* PETS-5: task and error events are observed without patching app.js. */
    document.addEventListener("copy-maker:task-complete", event => trigger("task-complete", event.detail || {}));
    document.addEventListener("stash:task-complete", event => trigger("task-complete", event.detail || {}));
    document.addEventListener("copy-maker:task-error", reportError);
    document.addEventListener("stash:task-error", reportError);
    document.addEventListener("copy-maker:streak-kept", () => trigger("streak-kept"));
    document.addEventListener("copy-maker:streak-broken", () => trigger("streak-broken"));
    document.addEventListener("copy-maker:focus-start", () => { focusStartedAt = Date.now(); focusMoodSent = false; trigger("focus-start"); });
    document.addEventListener("copy-maker:focus-complete", () => { trigger("focus-complete"); focusStartedAt = 0; focusMoodSent = false; });
    document.addEventListener("copy-maker:workspace-ready", () => { initializeEngine(); attachTaskObserver(); updateVisibility(); });
    document.addEventListener("copy-maker:sign-out", () => { companionVisible = false; root.hidden = true; stage.hidden = true; window.StashLegacyCompanion?.hide(); });
    app.addEventListener("click", event => {
        if (isLegacyActive() || event.target.closest("#avaPetWidget")) return;
        trigger("activity");
        if (event.target.closest("button, input, textarea, select, .copy-row")) {
            focusStartedAt ||= Date.now();
            focusMoodSent = false;
        }
    }, { passive: true });
    document.addEventListener("keydown", event => {
        if (isLegacyActive() || event.repeat || event.isComposing || event.key.length !== 1) return;
        if (!event.target.closest?.("input, textarea, [contenteditable='true']")) return;
        const now = Date.now();
        while (typingTimes.length && now - typingTimes[0] >= cssMs("--pet5-typing-window")) typingTimes.shift();
        typingTimes.push(now);
        if (typingTimes.length >= 14 && now - lastRapidTypingAt > cssMs("--pet5-typing-cooldown")) {
            lastRapidTypingAt = now;
            trigger("rapid-typing");
        }
    });
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            hiddenAt = Date.now();
            return;
        }
        if (hiddenAt && Date.now() - hiddenAt >= cssMs("--pet5-return-threshold")) {
            const daysAway = Math.max(1, Math.floor((Date.now() - hiddenAt) / 86400000));
            trigger("user-return", { daysAway });
        }
        hiddenAt = 0;
        updateVisibility();
    });

    const appObserver = new MutationObserver(() => {
        initializeEngine();
        updateVisibility();
    });
    appObserver.observe(app, { attributes: true, attributeFilter: ["hidden"] });
    const legacyObserver = legacyWidget ? new MutationObserver(() => {
        updateVisibility();
    }) : null;
    legacyObserver?.observe(legacyWidget, { attributes: true, attributeFilter: ["hidden"] });
    const errorObserver = new MutationObserver(records => {
        for (const record of records) {
            if (record.type === "characterData") inspectErrorNode(record.target.parentElement);
            else {
                if (record.target instanceof Element && record.target.matches('[role="alert"], [data-kind="error"], .settings-status, .provider-message, .auth-message')) inspectErrorNode(record.target);
                record.addedNodes.forEach(inspectErrorNode);
            }
        }
    });
    errorObserver.observe(document.body, { childList: true, characterData: true, subtree: true });

    window.addEventListener("copy-maker:task-error", reportError);
    window.addEventListener("stash:task-error", reportError);
    window.addEventListener("stash:ava-voice-error", reportError);

    /* PETS-5: clock triggers stay gentle and never nag while the legacy pet is selected. */
    tickTimer = window.setInterval(() => {
        if (!app.hidden && !isLegacyActive() && !allHidden && !document.hidden) engine.tick();
        updateFocusSession();
    }, cssMs("--pet5-tick-interval"));
    let lastDayPart = (() => {
        const hour = new Date().getHours();
        return hour >= 23 || hour < 6 ? "sleep" : hour >= 6 && hour < 10 ? "morning" : "day";
    })();
    timeCheckTimer = window.setInterval(() => {
        if (isLegacyActive() || allHidden || app.hidden || document.hidden) return;
        const hour = new Date().getHours();
        const part = hour >= 23 || hour < 6 ? "sleep" : hour >= 6 && hour < 10 ? "morning" : "day";
        if (part !== lastDayPart) {
            lastDayPart = part;
            if (part === "sleep") trigger("time-sleep");
            else if (part === "morning") trigger("time-of-day", { mood: activePet === "orbi" ? "focused" : "excited" });
        }
    }, cssMs("--pet5-time-check"));

    let initialActive = activePet;
    if (isLegacyActive()) {
        stage.hidden = true;
    } else {
        renderPet(initialActive);
        engine.setPet(initialActive);
    }
    setLegacyVoiceMuted(allMuted || !isLegacyActive());
    updateControls();
    initializeEngine();
    restorePosition();
    updateVisibility();
    attachTaskObserver();
})();
/* END PETS-5 */
