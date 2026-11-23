/* STASH-SPLASH: plain-web launch component with no external dependencies. */
(() => {
    const mount = document.getElementById("stashSplashMount");
    if (!mount) return;

    const STORAGE_KEY = "stashSplashSeenAt";
    const DAY_MS = 24 * 60 * 60 * 1000;
    const FULL_DURATION_MS = 2500;
    const REDUCED_DURATION_MS = 350;
    const FADE_DURATION_MS = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
        ? 100
        : 400;

    let lastSeenAt = 0;
    try {
        lastSeenAt = Number(localStorage.getItem(STORAGE_KEY));
    } catch (_) {
        // The splash still works when browser storage is disabled.
    }

    const now = Date.now();
    if (
        Number.isFinite(lastSeenAt) &&
        lastSeenAt > 0 &&
        now >= lastSeenAt &&
        now - lastSeenAt < DAY_MS
    ) {
        mount.remove();
        return;
    }

    const prefersReducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const previousFocus = document.activeElement;
    const lockedRegions = new Map();
    let leaving = false;
    let tabRequested = false;

    mount.className = "stash-splash-mount";
    mount.setAttribute("role", "dialog");
    mount.setAttribute("aria-modal", "true");
    mount.setAttribute("aria-label", "Starting Stash");
    mount.setAttribute("tabindex", "-1");
    mount.innerHTML = `
        <div class="stash-splash-content">
            <img class="stash-splash-logo" src="/ui/stash-logo.svg" alt="Stash">
            <div class="stash-splash-name">STASH</div>
            <div class="stash-splash-progress" role="progressbar" aria-label="Starting Stash" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
                <span class="stash-splash-progress-fill"></span>
            </div>
        </div>
    `;

    const lockBackground = () => {
        for (const id of ["authScreen", "app"]) {
            const region = document.getElementById(id);
            if (!region || lockedRegions.has(region)) continue;
            lockedRegions.set(region, region.inert);
            region.inert = true;
        }
    };

    lockBackground();
    const backgroundObserver = new MutationObserver(lockBackground);
    backgroundObserver.observe(document.body, { childList: true, subtree: true });
    mount.focus({ preventScroll: true });

    const focusFirstAvailableControl = () => {
        for (const id of ["authScreen", "app"]) {
            const region = document.getElementById(id);
            if (!region || region.hidden) continue;
            const control = region.querySelector(
                'input:not([disabled]), button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
            );
            if (control && control.getClientRects().length) {
                control.focus({ preventScroll: true });
                return;
            }
        }
    };

    const leaveSplash = () => {
        if (leaving) return;
        leaving = true;

        document.removeEventListener("click", skipSplash, true);
        document.removeEventListener("keydown", skipSplash, true);

        try {
            localStorage.setItem(STORAGE_KEY, String(Date.now()));
        } catch (_) {
            // Remembering the visit is optional when browser storage is disabled.
        }

        const progress = mount.querySelector(".stash-splash-progress");
        progress?.setAttribute("aria-valuenow", "100");
        mount.classList.add("stash-splash-leaving");

        window.setTimeout(() => {
            backgroundObserver.disconnect();
            for (const [region, wasInert] of lockedRegions) region.inert = wasInert;
            mount.remove();

            if (tabRequested) {
                focusFirstAvailableControl();
            } else if (
                previousFocus &&
                previousFocus !== document.body &&
                previousFocus !== mount &&
                previousFocus.isConnected
            ) {
                previousFocus.focus?.({ preventScroll: true });
            }
        }, FADE_DURATION_MS);
    };

    function skipSplash(event) {
        if (event.type === "keydown" && event.key === "Tab") {
            event.preventDefault();
            tabRequested = true;
        }
        leaveSplash();
    }

    document.addEventListener("click", skipSplash, true);
    document.addEventListener("keydown", skipSplash, true);

    window.setTimeout(
        leaveSplash,
        prefersReducedMotion ? REDUCED_DURATION_MS : FULL_DURATION_MS
    );
})();
