import { initializeApp } from "https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js";
import {
    OAuthProvider,
    RecaptchaVerifier,
    GoogleAuthProvider,
    browserSessionPersistence,
    getAuth,
    linkWithPhoneNumber,
    linkWithPopup,
    setPersistence,
    signInWithPhoneNumber,
    signInWithPopup,
    signOut,
} from "https://www.gstatic.com/firebasejs/11.10.0/firebase-auth.js";

const dialog = document.getElementById("providerDialog");
const message = document.getElementById("providerMessage");
const alternatives = document.getElementById("authAlternatives");
const setupNote = document.getElementById("authProviderNote");
const connectButton = document.getElementById("connectAuthButton");
const phoneFields = document.getElementById("phoneAuthFields");
const phoneInput = document.getElementById("phoneNumberInput");
const phoneConsent = document.getElementById("phoneConsent");
const sendCodeButton = document.getElementById("sendPhoneCodeButton");
const codeField = document.getElementById("phoneCodeField");
const codeInput = document.getElementById("phoneCodeInput");
const verifyCodeButton = document.getElementById("verifyPhoneCodeButton");

let firebaseAuth = null;
let authMode = "login";
let enabledProviders = ["google"];
let phoneConfirmation = null;
let recaptchaVerifier = null;

function setMessage(text = "") {
    if (message) message.textContent = text;
}

function providerError(error) {
    const errors = {
        "auth/operation-not-allowed": "That sign-in option is not enabled in Firebase yet.",
        "auth/popup-blocked": "Your browser blocked the sign-in window. Allow pop-ups and try again.",
        "auth/popup-closed-by-user": "The sign-in window was closed before it finished.",
        "auth/unauthorized-domain": "Add this website address to Firebase Authentication's authorized domains.",
        "auth/invalid-phone-number": "Enter a valid phone number with its country code, such as +14155552671.",
        "auth/too-many-requests": "Too many attempts. Wait a while and try again.",
        "auth/captcha-check-failed": "Phone verification could not complete. Refresh and try again.",
        "auth/provider-already-linked": "That sign-in option is already connected to this account.",
        "auth/credential-already-in-use": "That sign-in option belongs to another Firebase account. Sign in to that account first and link it there.",
    };
    return errors[error?.code] || error?.message || "Sign-in did not finish. Please try again.";
}

function setBusy(isBusy) {
    for (const id of [
        "googleProviderButton",
        "appleProviderButton",
        "phoneProviderButton",
        "sendPhoneCodeButton",
        "verifyPhoneCodeButton",
    ]) {
        const button = document.getElementById(id);
        if (button) button.disabled = isBusy || (id === "sendPhoneCodeButton" && !phoneConsent?.checked);
    }
}

async function connectServerSession(user) {
    const idToken = await user.getIdToken(true);
    const response = await fetch(authMode === "link" ? "/api/auth/link-firebase" : "/api/auth/firebase-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_token: idToken }),
        cache: "no-store",
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || "Stash could not finish sign-in.");
    return result;
}

async function finishAuthentication(user) {
    const result = await connectServerSession(user);
    setMessage(authMode === "link" ? "Sign-in option connected to this Stash account." : "Signed in. Opening Stash…");
    if (authMode === "link") {
        window.setTimeout(() => dialog?.close(), 900);
        return;
    }
    window.location.reload();
    return result;
}

function googleProvider() {
    const provider = new GoogleAuthProvider();
    provider.setCustomParameters({ prompt: "select_account" });
    return provider;
}

function appleProvider() {
    const provider = new OAuthProvider("apple.com");
    provider.addScope("email");
    provider.addScope("name");
    return provider;
}

async function signInWithProvider(provider) {
    setBusy(true);
    setMessage("");
    try {
        const currentUser = firebaseAuth.currentUser;
        const result = authMode === "link" && currentUser
            ? await linkWithPopup(currentUser, provider)
            : await signInWithPopup(firebaseAuth, provider);
        await finishAuthentication(result.user);
    } catch (error) {
        setMessage(providerError(error));
    } finally {
        setBusy(false);
    }
}

function resetRecaptcha() {
    if (!recaptchaVerifier) return;
    try {
        recaptchaVerifier.clear();
    } catch (_) {
        // A failed widget may already have been removed from the dialog.
    }
    recaptchaVerifier = null;
}

function getRecaptchaVerifier() {
    if (!recaptchaVerifier) {
        recaptchaVerifier = new RecaptchaVerifier(firebaseAuth, "phoneRecaptcha", {
            size: "invisible",
        });
    }
    return recaptchaVerifier;
}

async function requestPhoneCode() {
    const phone = (phoneInput?.value || "").replace(/[\s()-]/g, "");
    if (!/^\+[1-9]\d{6,14}$/.test(phone)) {
        setMessage("Enter your number with its country code, such as +14155552671.");
        phoneInput?.focus();
        return;
    }
    if (!phoneConsent?.checked) {
        setMessage("Please agree to phone verification before requesting a code.");
        phoneConsent?.focus();
        return;
    }

    setBusy(true);
    setMessage("");
    try {
        const verifier = getRecaptchaVerifier();
        const currentUser = firebaseAuth.currentUser;
        phoneConfirmation = authMode === "link" && currentUser
            ? await linkWithPhoneNumber(currentUser, phone, verifier)
            : await signInWithPhoneNumber(firebaseAuth, phone, verifier);
        if (codeField) codeField.hidden = false;
        if (verifyCodeButton) verifyCodeButton.hidden = false;
        if (sendCodeButton) sendCodeButton.textContent = "Send another code";
        setMessage("Code sent. Check your phone and enter the verification code.");
        codeInput?.focus();
    } catch (error) {
        resetRecaptcha();
        setMessage(providerError(error));
    } finally {
        setBusy(false);
    }
}

async function verifyPhoneCode() {
    const code = (codeInput?.value || "").trim();
    if (!phoneConfirmation || !code) {
        setMessage("Enter the code sent to your phone.");
        codeInput?.focus();
        return;
    }
    setBusy(true);
    setMessage("");
    try {
        const result = await phoneConfirmation.confirm(code);
        await finishAuthentication(result.user);
    } catch (error) {
        setMessage(providerError(error));
    } finally {
        setBusy(false);
    }
}

function openProviderDialog(mode) {
    if (!firebaseAuth || !dialog) return;
    authMode = mode;
    phoneConfirmation = null;
    resetRecaptcha();
    if (phoneFields) phoneFields.hidden = true;
    if (codeField) codeField.hidden = true;
    if (verifyCodeButton) verifyCodeButton.hidden = true;
    if (sendCodeButton) sendCodeButton.textContent = "Send verification code";
    if (phoneInput) phoneInput.value = "";
    if (phoneConsent) phoneConsent.checked = false;
    if (codeInput) codeInput.value = "";
    if (sendCodeButton) sendCodeButton.disabled = true;
    const title = document.getElementById("providerDialogTitle");
    const subtitle = document.getElementById("providerDialogSubtitle");
    const providerNames = enabledProviders.map(provider => ({
        google: "Google",
        apple: "Apple",
        phone: "phone",
    })[provider]).filter(Boolean);
    if (title) title.textContent = mode === "link" ? "Connect a sign-in option" : "Choose a sign-in option";
    if (subtitle) subtitle.textContent = mode === "link"
        ? `Connect ${providerNames.join(" or ")} to this Stash account for next time.`
        : `Use ${providerNames.join(" or ")} to open your Stash account.`;
    setMessage("");
    if (!dialog.open) dialog.showModal();
}

document.getElementById("chooseSignInButton")?.addEventListener("click", () => openProviderDialog("login"));
connectButton?.addEventListener("click", () => openProviderDialog("link"));
document.getElementById("closeProviderDialog")?.addEventListener("click", () => dialog?.close());
document.getElementById("googleProviderButton")?.addEventListener("click", () => signInWithProvider(googleProvider()));
document.getElementById("appleProviderButton")?.addEventListener("click", () => signInWithProvider(appleProvider()));
document.getElementById("phoneProviderButton")?.addEventListener("click", () => {
    if (phoneFields) phoneFields.hidden = !phoneFields.hidden;
    setMessage("");
    if (!phoneFields?.hidden) phoneInput?.focus();
});
phoneConsent?.addEventListener("change", () => {
    if (sendCodeButton) sendCodeButton.disabled = !phoneConsent.checked;
});
sendCodeButton?.addEventListener("click", requestPhoneCode);
verifyCodeButton?.addEventListener("click", verifyPhoneCode);
document.getElementById("phoneCodeInput")?.addEventListener("keydown", event => {
    if (event.key === "Enter") verifyPhoneCode();
});
dialog?.addEventListener("click", event => {
    if (event.target === dialog) dialog.close();
});
document.addEventListener("copy-maker:sign-out", () => {
    if (firebaseAuth) signOut(firebaseAuth).catch(() => {});
});

async function initializeProviderOptions() {
    try {
        const response = await fetch("/api/auth/status", { cache: "no-store" });
        const status = await response.json();
        if (!status.firebase_configured || !status.firebase_config) return;

        enabledProviders = Array.isArray(status.firebase_enabled_providers)
            ? status.firebase_enabled_providers
            : ["google"];
        const googleButton = document.getElementById("googleProviderButton");
        const appleButton = document.getElementById("appleProviderButton");
        const phoneButton = document.getElementById("phoneProviderButton");
        if (googleButton) googleButton.hidden = !enabledProviders.includes("google");
        if (appleButton) appleButton.hidden = !enabledProviders.includes("apple");
        if (phoneButton) phoneButton.hidden = !enabledProviders.includes("phone");

        const app = initializeApp(status.firebase_config, "copy-maker-auth");
        firebaseAuth = getAuth(app);
        await setPersistence(firebaseAuth, browserSessionPersistence);
        if (alternatives) alternatives.hidden = enabledProviders.length === 0;
        if (setupNote) setupNote.hidden = true;
        if (connectButton) connectButton.hidden = enabledProviders.length === 0;
    } catch (error) {
        if (setupNote) {
            setupNote.hidden = false;
            setupNote.textContent = "Google, Apple, and phone sign-in could not start. Check the Firebase setup and refresh.";
        }
    }
}

initializeProviderOptions();
