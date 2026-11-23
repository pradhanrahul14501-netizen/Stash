/* PETS-5: original inline SVG components for Orbi, Pixel, Sage, Zap, and Mochi. */
(() => {
    "use strict";

    const wrap = art => `<svg class="pet5-art" viewBox="0 0 100 100" aria-hidden="true" focusable="false">${art}</svg>`;

    /* PETS-5: ORBI — a glass orb with a calm inner light. */
    const orbi = () => wrap(`
        <ellipse class="pet5-shadow" cx="50" cy="89" rx="25" ry="5" />
        <circle class="pet5-body pet5-orb" cx="50" cy="49" r="37" />
        <ellipse class="pet5-shine" cx="36" cy="27" rx="10" ry="5" />
        <path class="pet5-orb-ring" d="M19 61c8 17 38 27 59 8" />
        <g class="pet5-eye-group pet5-eye-track">
            <ellipse class="pet5-eye" cx="39" cy="48" rx="3.4" ry="5" />
            <ellipse class="pet5-eye" cx="61" cy="48" rx="3.4" ry="5" />
            <circle class="pet5-pupil" cx="39.8" cy="48.6" r="1.5" />
            <circle class="pet5-pupil" cx="61.8" cy="48.6" r="1.5" />
        </g>
        <path class="pet5-brow" d="M33 39q6-3 11 0m12 0q5-3 11 0" />
        <path class="pet5-mouth" d="M43 61q7 5 14 0" />
        <circle class="pet5-cheek" cx="30" cy="58" r="3" />
        <circle class="pet5-cheek" cx="70" cy="58" r="3" />
    `);

    /* PETS-5: PIXEL — a chunky, friendly retro blob. */
    const pixel = () => wrap(`
        <ellipse class="pet5-shadow" cx="50" cy="89" rx="25" ry="5" />
        <path class="pet5-body pet5-pixel-body" d="M30 16h38v8h8v10h6v33h-8v10H65v8H35v-8H24v-9h-8V35h8V24h6z" />
        <rect class="pet5-pixel-shine" x="30" y="26" width="8" height="5" />
        <g class="pet5-eye-group pet5-eye-track">
            <rect class="pet5-eye" x="34" y="43" width="8" height="10" rx="1" />
            <rect class="pet5-eye" x="59" y="43" width="8" height="10" rx="1" />
            <rect class="pet5-pupil" x="38" y="47" width="3" height="4" />
            <rect class="pet5-pupil" x="63" y="47" width="3" height="4" />
        </g>
        <path class="pet5-brow" d="M33 38h12m13 0h12" />
        <path class="pet5-mouth" d="M42 63h6v4h8v-4h5" />
        <path class="pet5-heart" d="M49 76c-5-4-9-7-9-11a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 4-4 7-9 11z" />
        <path class="pet5-pixel-spark" d="M17 27h6v6h-6zm61 37h6v6h-6z" />
    `);

    /* PETS-5: SAGE — a soft owl with feather tufts and half-lidded eyes. */
    const sage = () => wrap(`
        <ellipse class="pet5-shadow" cx="50" cy="89" rx="26" ry="5" />
        <path class="pet5-ear-tuft" d="M23 34 17 14l22 12m38 8 6-20-22 12" />
        <ellipse class="pet5-body pet5-owl-body" cx="50" cy="53" rx="34" ry="33" />
        <path class="pet5-wing" d="M21 53q-7 16 7 24m51-24q7 16-7 24" />
        <ellipse class="pet5-face-patch" cx="39" cy="48" rx="13" ry="15" />
        <ellipse class="pet5-face-patch" cx="61" cy="48" rx="13" ry="15" />
        <g class="pet5-eye-group pet5-eye-track">
            <circle class="pet5-eye" cx="40" cy="48" r="5" />
            <circle class="pet5-eye" cx="60" cy="48" r="5" />
            <circle class="pet5-pupil" cx="41" cy="49" r="2" />
            <circle class="pet5-pupil" cx="61" cy="49" r="2" />
        </g>
        <path class="pet5-brow" d="M31 39q8-5 16 1m6 0q8-6 16-1" />
        <path class="pet5-beak" d="m46 59 4 6 4-6z" />
        <path class="pet5-foot" d="M38 83v5m-4 0h8m20-5v5m-4 0h8" />
    `);

    /* PETS-5: ZAP — an energetic electric critter with static sparks. */
    const zap = () => wrap(`
        <ellipse class="pet5-shadow" cx="50" cy="89" rx="24" ry="5" />
        <path class="pet5-spark" d="m24 22-4 11h7l-4 9 13-14h-8l5-6zm52 1-3 9h6l-3 8 11-11h-7l4-6z" />
        <path class="pet5-body pet5-zap-body" d="M25 35q2-18 25-18 22 0 26 18l-4 33q-2 16-22 16T28 68z" />
        <path class="pet5-zap-fin" d="m33 29-10-9 3 17m41-8 10-9-3 17" />
        <g class="pet5-eye-group pet5-eye-track">
            <ellipse class="pet5-eye" cx="39" cy="46" rx="4" ry="6" />
            <ellipse class="pet5-eye" cx="61" cy="46" rx="4" ry="6" />
            <circle class="pet5-pupil" cx="40" cy="47" r="1.8" />
            <circle class="pet5-pupil" cx="62" cy="47" r="1.8" />
        </g>
        <path class="pet5-brow" d="M31 36q8-4 14 1m10-1q7-4 14 0" />
        <path class="pet5-mouth" d="M40 63q10 9 20 0" />
        <path class="pet5-zap-stripe" d="m53 58-8 9h7l-4 8 12-12h-7z" />
        <circle class="pet5-cheek" cx="29" cy="58" r="3" />
        <circle class="pet5-cheek" cx="71" cy="58" r="3" />
    `);

    /* PETS-5: MOCHI — a sleepy round cat with soft ears and whiskers. */
    const mochi = () => wrap(`
        <ellipse class="pet5-shadow" cx="50" cy="89" rx="27" ry="5" />
        <path class="pet5-tail" d="M75 69q18 1 14-13-2-7-9-5" />
        <path class="pet5-ear" d="m21 41 4-27 21 18m13 0 21-18 4 27" />
        <circle class="pet5-body pet5-cat-body" cx="50" cy="54" r="34" />
        <path class="pet5-inner-ear" d="m29 27 2 15 10-10m30-5-2 15-10-10" />
        <g class="pet5-eye-group pet5-eye-track">
            <ellipse class="pet5-eye" cx="39" cy="49" rx="3.4" ry="4.8" />
            <ellipse class="pet5-eye" cx="61" cy="49" rx="3.4" ry="4.8" />
            <circle class="pet5-pupil" cx="40" cy="50" r="1.5" />
            <circle class="pet5-pupil" cx="62" cy="50" r="1.5" />
        </g>
        <path class="pet5-brow" d="M33 42q6-3 11 0m12 0q5-3 11 0" />
        <path class="pet5-nose" d="m47 59 3 2 3-2z" />
        <path class="pet5-mouth" d="M50 61v3m0 0q-5 5-9 0m9 0q5 5 9 0" />
        <path class="pet5-whisker" d="m31 59-14-3m14 8-14 2m52-7 14-3m-14 8 14 2" />
        <ellipse class="pet5-paw" cx="39" cy="82" rx="8" ry="5" />
        <ellipse class="pet5-paw" cx="61" cy="82" rx="8" ry="5" />
    `);

    const COMPONENTS = {
        orbi: { render: orbi, trick: "A slow orbit, then a soft sparkle.", trickName: "orbit" },
        pixel: { render: pixel, trick: "Pixel breakdance! Combo unlocked.", trickName: "pixel-party" },
        sage: { render: sage, trick: "Sage gives a thoughtful wing-flap.", trickName: "wing-flap" },
        zap: { render: zap, trick: "Zap makes a tiny thunderbolt burst.", trickName: "zap-burst" },
        mochi: { render: mochi, trick: "Mochi curls into a sleepy loaf.", trickName: "loaf" },
    };

    window.Pet5Components = { COMPONENTS };
})();
/* END PETS-5 */
