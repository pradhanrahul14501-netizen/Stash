/* STASH-COMPANIONS: one registry drives every companion selector and picker. */
(() => {
    "use strict";

    const COMPANIONS = [
        { id: "ava", name: "Ava", description: "Robot", kind: "legacy", legacyId: "ava" },
        { id: "pip", name: "Pip", description: "Fox", kind: "legacy", legacyId: "pip" },
        { id: "mochi-cloud", name: "Mochi", description: "Cloud", kind: "legacy", legacyId: "mochi" },
        { id: "byte", name: "Byte", description: "Dino", kind: "legacy", legacyId: "byte" },
        { id: "orbi", name: "Orbi", description: "Focus buddy", kind: "pet5" },
        { id: "pixel", name: "Pixel", description: "Retro gamer", kind: "pet5" },
        { id: "sage", name: "Sage", description: "Wise owl", kind: "pet5" },
        { id: "zap", name: "Zap", description: "Hype creature", kind: "pet5" },
        { id: "mochi", name: "Mochi", description: "Cozy cat", kind: "pet5" },
    ].map(companion => Object.freeze(companion));

    window.StashCompanions = Object.freeze({
        all: Object.freeze(COMPANIONS),
        get(id) { return COMPANIONS.find(companion => companion.id === id) || null; },
        legacyChoices: Object.freeze(COMPANIONS.filter(companion => companion.kind === "legacy")),
    });
})();
