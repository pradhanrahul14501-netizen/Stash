import { initializeApp } from "https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js";
import {
    browserSessionPersistence,
    createUserWithEmailAndPassword,
    getAuth,
    RecaptchaVerifier,
    reload,
    sendEmailVerification,
    setPersistence,
    signInWithEmailAndPassword,
    signInWithPhoneNumber,
    signOut,
} from "https://www.gstatic.com/firebasejs/11.10.0/firebase-auth.js";

(() => {
    const authCard = document.getElementById("sharedAuthCard");
    const authForm = document.getElementById("sharedAuthForm");
    const legacyAuthForm = document.getElementById("sharedLegacyAuthForm");
    const authTitle = document.getElementById("sharedAuthTitle");
    const authSubmit = document.getElementById("sharedAuthSubmit");
    const authPassword = document.getElementById("sharedPassword");
    const authEmail = document.getElementById("sharedEmail");
    const authModeButton = document.getElementById("sharedAuthModeButton");
    const authMessage = document.getElementById("sharedAuthMessage");
    const phoneInput = document.getElementById("sharedPhoneNumber");
    const phoneConsent = document.getElementById("sharedPhoneConsent");
    const sendPhoneCodeButton = document.getElementById("sharedSendPhoneCode");
    const phoneCodeField = document.getElementById("sharedPhoneCodeField");
    const phoneCodeInput = document.getElementById("sharedPhoneCode");
    const verifyPhoneCodeButton = document.getElementById("sharedVerifyPhoneCode");
    const workspace = document.getElementById("sharedWorkspace");
    const unavailable = document.getElementById("sharedUnavailable");
    const logoutButton = document.getElementById("sharedLogoutButton");
    const usernameLabel = document.getElementById("sharedUsernameLabel");
    const cloudStatus = document.getElementById("sharedCloudStatus");
    const filePicker = document.getElementById("sharedFilePicker");
    const uploadMessage = document.getElementById("sharedUploadMessage");
    const linkForm = document.getElementById("sharedLinkForm");
    const linkInput = document.getElementById("sharedLinkInput");
    const linkSubmit = document.getElementById("sharedLinkSubmit");
    const linkMessage = document.getElementById("sharedLinkMessage");
    const pairingButton = document.getElementById("sharedCreatePairingButton");
    const pairingCode = document.getElementById("sharedPairingCode");
    const pairingNote = document.getElementById("sharedPairingNote");
    const refreshExtensionsButton = document.getElementById("sharedRefreshExtensionsButton");
    const extensionsList = document.getElementById("sharedExtensionsList");
    const extensionsEmpty = document.getElementById("sharedExtensionsEmpty");
    const refreshButton = document.getElementById("sharedRefreshButton");
    const libraryGrid = document.getElementById("sharedLibraryGrid");
    const libraryEmpty = document.getElementById("sharedLibraryEmpty");

    let signInMode = false;
    let firebaseAuth = null;
    let phoneConfirmation = null;
    let recaptchaVerifier = null;

    function setMessage(element, message, kind = "") {
        if (!element) return;
        element.textContent = message;
        if (kind) element.dataset.kind = kind;
        else delete element.dataset.kind;
    }

    function formatSize(bytes) {
        const value = Number(bytes) || 0;
        if (value >= 1024 ** 3) return (value / (1024 ** 3)).toFixed(2) + " GB";
        if (value >= 1024 ** 2) return (value / (1024 ** 2)).toFixed(1) + " MB";
        if (value >= 1024) return Math.round(value / 1024) + " KB";
        return value ? value + " B" : "";
    }

    function safeMediaUrl(value) {
        if (typeof value !== "string" || !value) return "";
        try {
            const url = new URL(value, window.location.origin);
            return url.origin === window.location.origin && url.pathname.startsWith("/api/shared/media/")
                ? url.href
                : "";
        } catch {
            return "";
        }
    }

    function safeOpenUrl(value) {
        if (typeof value !== "string" || !value) return "";
        try {
            const url = new URL(value, window.location.origin);
            if (
                !["http:", "https:"].includes(url.protocol) ||
                url.username || url.password
            ) return "";
            return url.href;
        } catch {
            return "";
        }
    }

    async function requestJson(url, options = {}) {
        const response = await fetch(url, {
            credentials: "same-origin",
            ...options,
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.error || "Stash could not complete that request.");
        }
        return payload;
    }

    function showUnavailable() {
        authCard.hidden = true;
        workspace.hidden = true;
        unavailable.hidden = false;
    }

    function updateAuthMode() {
        signInMode = !signInMode;
        authTitle.textContent = signInMode ? "Welcome back" : "Create your Stash account";
        authSubmit.textContent = signInMode ? "Sign in" : "Create account";
        authPassword.autocomplete = signInMode ? "current-password" : "new-password";
        authPassword.minLength = signInMode ? 6 : 12;
        authModeButton.textContent = signInMode
            ? "Create a new account"
            : "I already have an account";
        setMessage(authMessage, "");
    }

    function firebaseErrorMessage(error) {
        const messages = {
            "auth/operation-not-allowed": "Enable Email/Password and Phone in Firebase Authentication settings.",
            "auth/unauthorized-domain": "Add this website hostname to Firebase Authentication’s Authorized domains.",
            "auth/email-already-in-use": "That email already has a Stash account. Choose sign in instead.",
            "auth/invalid-email": "Enter a valid email address.",
            "auth/weak-password": "Use a password with at least 12 characters.",
            "auth/invalid-credential": "Email or password is incorrect.",
            "auth/user-not-found": "No Stash account was found for that email.",
            "auth/wrong-password": "Email or password is incorrect.",
            "auth/invalid-phone-number": "Enter your phone number with country code, such as +14155552671.",
            "auth/too-many-requests": "Too many attempts. Wait a while and try again.",
            "auth/captcha-check-failed": "Phone verification could not complete. Refresh the page and try again.",
            "auth/invalid-verification-code": "That SMS code is incorrect. Check it and try again.",
            "auth/code-expired": "That SMS code expired. Request a new code.",
            "auth/network-request-failed": "The internet connection failed. Check it and try again.",
        };
        return messages[error?.code] || error?.message || "Sign-in did not finish. Please try again.";
    }

    function clearRecaptcha() {
        if (!recaptchaVerifier) return;
        try {
            recaptchaVerifier.clear();
        } catch (_) {
            // The invisible widget may already have been removed by Firebase.
        }
        recaptchaVerifier = null;
    }

    function getRecaptchaVerifier() {
        if (!recaptchaVerifier) {
            recaptchaVerifier = new RecaptchaVerifier(firebaseAuth, "sharedPhoneRecaptcha", {
                size: "invisible",
            });
        }
        return recaptchaVerifier;
    }

    async function connectSharedSession(user, requireVerifiedEmail = false) {
        if (requireVerifiedEmail) await reload(user);
        if (requireVerifiedEmail && !user.emailVerified) {
            await sendEmailVerification(user);
            setMessage(authMessage, "Verify your email using the link we sent, then sign in again.", "success");
            return false;
        }
        const idToken = await user.getIdToken(true);
        const result = await requestJson("/api/shared/firebase-login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id_token: idToken }),
        });
        setMessage(authMessage, result.newWorkspace
            ? "Your new private Stash workspace is ready."
            : "Welcome back. Opening your Stash workspace…", "success");
        window.location.reload();
        return true;
    }

    async function initializeFirebase(config) {
        if (!config) return false;
        try {
            const firebaseApp = initializeApp(config, "stash-shared");
            firebaseAuth = getAuth(firebaseApp);
            await setPersistence(firebaseAuth, browserSessionPersistence);
            return true;
        } catch (error) {
            setMessage(authMessage, "Firebase sign-in could not start. Check the Firebase web app configuration.", "error");
            return false;
        }
    }

    function showWorkspace(status) {
        authCard.hidden = true;
        unavailable.hidden = true;
        workspace.hidden = false;
        logoutButton.hidden = false;
        usernameLabel.textContent = status.username || "there";
        cloudStatus.textContent = status.cloudReady
            ? status.storageMode === "local" ? "This Mac’s storage ready" : "Cloud storage ready"
            : "Cloud storage needs setup";
        cloudStatus.dataset.ready = String(Boolean(status.cloudReady));
    }

    function showShareResult() {
        const params = new URLSearchParams(window.location.search);
        const result = params.get("share");
        if (!result) return;

        if (result === "login") {
            setMessage(authMessage, "Sign in to Stash, then share the item again.", "error");
        } else if (result === "saved") {
            setMessage(uploadMessage, "Saved to your private Stash library.", "success");
        } else if (result === "link") {
            setMessage(uploadMessage, "Saved the page link. To save the video file, share or choose the video itself.", "success");
        } else {
            setMessage(uploadMessage, "Stash could not save that shared item. Please try again.", "error");
        }

        params.delete("share");
        const query = params.toString();
        window.history.replaceState(
            null,
            "",
            window.location.pathname + (query ? "?" + query : "") + window.location.hash,
        );
    }

    function previewFor(item) {
        const preview = document.createElement("div");
        preview.className = "shared-library-preview";
        const mediaUrl = safeMediaUrl(item.url);
        if (mediaUrl && String(item.mime_type || "").startsWith("video/")) {
            const video = document.createElement("video");
            video.src = mediaUrl;
            video.controls = true;
            video.preload = "metadata";
            preview.append(video);
        } else if (mediaUrl && String(item.mime_type || "").startsWith("audio/")) {
            const audio = document.createElement("audio");
            audio.src = mediaUrl;
            audio.controls = true;
            preview.append(audio);
        } else if (mediaUrl && String(item.mime_type || "").startsWith("image/")) {
            const image = document.createElement("img");
            image.src = mediaUrl;
            image.alt = item.original_name || "Saved image";
            preview.append(image);
        } else {
            const icon = document.createElement("span");
            icon.className = "shared-library-icon";
            icon.textContent = item.type === "text" ? "T" : item.type === "link" ? "↗" : "□";
            preview.append(icon);
        }
        return preview;
    }

    async function deleteItem(itemId, card) {
        const confirmed = window.confirm("Remove this saved item from your private Stash library?");
        if (!confirmed) return;
        try {
            await requestJson("/api/shared/library/" + encodeURIComponent(itemId), {
                method: "DELETE",
            });
            card.remove();
            libraryEmpty.hidden = libraryGrid.childElementCount > 0;
        } catch (error) {
            window.alert(error.message);
        }
    }

    function renderLibrary(items) {
        libraryGrid.replaceChildren();
        libraryEmpty.hidden = items.length > 0;
        for (const item of items) {
            const card = document.createElement("article");
            card.className = "shared-library-item";
            card.append(previewFor(item));

            const copy = document.createElement("div");
            copy.className = "shared-library-copy";
            const name = document.createElement("div");
            name.className = "shared-library-name";
            name.textContent = item.original_name || "Saved copy";
            name.title = name.textContent;
            const meta = document.createElement("div");
            meta.className = "shared-library-meta";
            const created = item.created_at ? new Date(item.created_at).toLocaleDateString() : "";
            meta.textContent = [item.type, formatSize(item.size), created].filter(Boolean).join(" · ");
            const organization = document.createElement("div");
            organization.className = "shared-library-organization";
            const organizationLabels = [];
            if (item.folder_name) organizationLabels.push("Folder: " + item.folder_name);
            if (Array.isArray(item.tags)) {
                item.tags.slice(0, 12).forEach((tag) => organizationLabels.push("#" + String(tag).slice(0, 24)));
            }
            if (item.favorite) organizationLabels.push("Favorite");
            organization.textContent = organizationLabels.join(" · ");
            organization.hidden = organizationLabels.length === 0;
            const actions = document.createElement("div");
            actions.className = "shared-library-actions";
            const openUrl = safeOpenUrl(item.url);
            if (openUrl) {
                const open = document.createElement("a");
                open.className = "shared-library-link";
                open.href = openUrl;
                open.target = "_blank";
                open.rel = "noopener";
                open.textContent = "Open";
                actions.append(open);
            } else {
                actions.append(document.createElement("span"));
            }
            const remove = document.createElement("button");
            remove.className = "shared-delete-button";
            remove.type = "button";
            remove.textContent = "Remove";
            remove.addEventListener("click", () => deleteItem(item.id, card));
            actions.append(remove);
            copy.append(name, meta, organization, actions);
            card.append(copy);
            libraryGrid.append(card);
        }
    }

    function formatExtensionTime(value) {
        if (!value) return "Not used yet";
        return "Last used " + new Date(Number(value) * 1000).toLocaleString();
    }

    async function revokeExtension(installationId, row) {
        if (!window.confirm("Disconnect this browser from your Stash account?")) return;
        try {
            await requestJson("/api/shared/extensions/" + encodeURIComponent(installationId), {
                method: "DELETE",
            });
            row.remove();
            extensionsEmpty.hidden = extensionsList.childElementCount > 0;
        } catch (error) {
            window.alert(error.message);
        }
    }

    function renderExtensions(installations) {
        extensionsList.replaceChildren();
        extensionsEmpty.hidden = installations.length > 0;
        for (const installation of installations) {
            const row = document.createElement("li");
            row.className = "shared-extension-row";
            const details = document.createElement("div");
            const name = document.createElement("div");
            name.className = "shared-extension-name";
            name.textContent = installation.label || "Chrome extension";
            const meta = document.createElement("div");
            meta.className = "shared-extension-meta";
            meta.textContent = formatExtensionTime(installation.lastUsedAt);
            details.append(name, meta);
            const disconnect = document.createElement("button");
            disconnect.type = "button";
            disconnect.className = "shared-delete-button";
            disconnect.textContent = "Disconnect";
            disconnect.addEventListener("click", () => revokeExtension(installation.id, row));
            row.append(details, disconnect);
            extensionsList.append(row);
        }
    }

    async function refreshExtensions() {
        refreshExtensionsButton.disabled = true;
        try {
            const installations = await requestJson("/api/shared/extensions", { cache: "no-store" });
            renderExtensions(Array.isArray(installations) ? installations : []);
        } catch (error) {
            pairingNote.textContent = error.message;
        } finally {
            refreshExtensionsButton.disabled = false;
        }
    }

    async function refreshLibrary() {
        refreshButton.disabled = true;
        try {
            const items = await requestJson("/api/shared/library", { cache: "no-store" });
            renderLibrary(Array.isArray(items) ? items : []);
        } catch (error) {
            setMessage(uploadMessage, error.message, "error");
        } finally {
            refreshButton.disabled = false;
        }
    }

    async function initialize() {
        try {
            const status = await requestJson("/api/shared/status", { cache: "no-store" });
            if (!status.sharedMode) {
                showUnavailable();
                return;
            }
            if (!status.authenticated) {
                const configured = await initializeFirebase(status.firebaseConfig);
                if (!configured) {
                    setMessage(authMessage, "Email and phone accounts need Firebase Authentication set up on this server.", "error");
                }
            }
            if (!status.authenticated && status.registrationOpen === false) {
                signInMode = true;
                authTitle.textContent = "Welcome back";
                authSubmit.textContent = "Sign in";
                authPassword.autocomplete = "current-password";
                authPassword.minLength = 6;
                authModeButton.hidden = true;
                document.querySelector(".shared-auth-alternative summary").textContent = "Sign in with an existing phone account. New registrations are closed.";
            }
            if (status.authenticated) {
                showWorkspace(status);
                await Promise.all([refreshLibrary(), refreshExtensions()]);
            }
            showShareResult();
        } catch (error) {
            showUnavailable();
        }
    }

    authModeButton.addEventListener("click", updateAuthMode);

    authForm.addEventListener("submit", async event => {
        event.preventDefault();
        if (!firebaseAuth) {
            setMessage(authMessage, "Firebase Authentication is not configured yet.", "error");
            return;
        }
        const email = authEmail.value.trim().toLowerCase();
        const password = authPassword.value;
        const signingIn = signInMode;
        authSubmit.disabled = true;
        setMessage(authMessage, signingIn ? "Signing in…" : "Creating your account…");
        try {
            let result;
            if (signingIn) {
                result = await signInWithEmailAndPassword(firebaseAuth, email, password);
            } else {
                result = await createUserWithEmailAndPassword(firebaseAuth, email, password);
                await sendEmailVerification(result.user);
                setMessage(authMessage, "Account started. Check your email and verify it before signing in.", "success");
                authForm.reset();
                return;
            }
            await connectSharedSession(result.user, signingIn);
        } catch (error) {
            setMessage(authMessage, firebaseErrorMessage(error), "error");
        } finally {
            authSubmit.disabled = false;
        }
    });

    phoneConsent.addEventListener("change", () => {
        sendPhoneCodeButton.disabled = !phoneConsent.checked;
    });

    sendPhoneCodeButton.addEventListener("click", async () => {
        const phone = phoneInput.value.replace(/[\s()-]/g, "");
        if (!/^\+[1-9]\d{6,14}$/.test(phone)) {
            setMessage(authMessage, "Enter your number with country code, such as +14155552671.", "error");
            phoneInput.focus();
            return;
        }
        if (!phoneConsent.checked) {
            setMessage(authMessage, "Agree to SMS verification before requesting a code.", "error");
            return;
        }
        if (!firebaseAuth) {
            setMessage(authMessage, "Firebase Authentication is not configured yet.", "error");
            return;
        }
        sendPhoneCodeButton.disabled = true;
        setMessage(authMessage, "Sending a verification code…");
        try {
            phoneConfirmation = await signInWithPhoneNumber(firebaseAuth, phone, getRecaptchaVerifier());
            phoneCodeField.hidden = false;
            verifyPhoneCodeButton.hidden = false;
            sendPhoneCodeButton.textContent = "Send another code";
            setMessage(authMessage, "Code sent. Enter the SMS code to open your Stash workspace.", "success");
            phoneCodeInput.focus();
        } catch (error) {
            clearRecaptcha();
            setMessage(authMessage, firebaseErrorMessage(error), "error");
        } finally {
            sendPhoneCodeButton.disabled = !phoneConsent.checked;
        }
    });

    verifyPhoneCodeButton.addEventListener("click", async () => {
        if (!phoneConfirmation || !phoneCodeInput.value.trim()) {
            setMessage(authMessage, "Enter the SMS verification code.", "error");
            phoneCodeInput.focus();
            return;
        }
        verifyPhoneCodeButton.disabled = true;
        setMessage(authMessage, "Verifying your phone…");
        try {
            const result = await phoneConfirmation.confirm(phoneCodeInput.value.trim());
            await connectSharedSession(result.user);
        } catch (error) {
            setMessage(authMessage, firebaseErrorMessage(error), "error");
        } finally {
            verifyPhoneCodeButton.disabled = false;
        }
    });

    legacyAuthForm.addEventListener("submit", async event => {
        event.preventDefault();
        const username = document.getElementById("sharedLegacyUsername").value.trim();
        const password = document.getElementById("sharedLegacyPassword").value;
        const button = legacyAuthForm.querySelector("button[type='submit']");
        button.disabled = true;
        setMessage(authMessage, "Signing in to your older account…");
        try {
            await requestJson("/api/shared/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password }),
            });
            window.location.reload();
        } catch (error) {
            setMessage(authMessage, error.message, "error");
        } finally {
            button.disabled = false;
        }
    });

    logoutButton.addEventListener("click", async () => {
        logoutButton.disabled = true;
        try {
            await requestJson("/api/shared/logout", { method: "POST" });
            if (firebaseAuth) await signOut(firebaseAuth);
        } catch (error) {
            window.alert(error.message);
        } finally {
            window.location.reload();
        }
    });

    filePicker.addEventListener("change", async () => {
        const files = Array.from(filePicker.files || []);
        if (!files.length) return;
        filePicker.disabled = true;
        try {
            for (const file of files) {
                setMessage(uploadMessage, "Uploading " + file.name + "…");
                const body = new FormData();
                body.append("file", file, file.name);
                await requestJson("/api/shared/upload", { method: "POST", body });
            }
            setMessage(uploadMessage, "Saved to your private Stash library.", "success");
            await refreshLibrary();
        } catch (error) {
            setMessage(uploadMessage, error.message, "error");
        } finally {
            filePicker.value = "";
            filePicker.disabled = false;
        }
    });

    linkForm.addEventListener("submit", async event => {
        event.preventDefault();
        const rawUrl = linkInput.value.trim();
        let url;
        try {
            url = new URL(rawUrl);
            if (!new Set(["http:", "https:"]).has(url.protocol)) throw new Error();
        } catch {
            setMessage(linkMessage, "Enter a full http or https page address.", "error");
            return;
        }

        linkSubmit.disabled = true;
        setMessage(linkMessage, "Saving page link…");
        try {
            await requestJson("/api/shared/share", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url: url.href, title: url.hostname }),
            });
            linkForm.reset();
            setMessage(linkMessage, "Saved the page link. To save the video file, choose it from Photos or Files.", "success");
            await refreshLibrary();
        } catch (error) {
            setMessage(linkMessage, error.message, "error");
        } finally {
            linkSubmit.disabled = false;
        }
    });

    pairingButton.addEventListener("click", async () => {
        pairingButton.disabled = true;
        try {
            const pairing = await requestJson("/api/shared/pairing-code", {
                method: "POST",
            });
            pairingCode.hidden = false;
            pairingCode.textContent = pairing.code;
            pairingNote.textContent = "Open the Stash extension in Chrome, enter this code, then select Connect. It expires in 10 minutes.";
        } catch (error) {
            pairingNote.textContent = error.message;
        } finally {
            pairingButton.disabled = false;
        }
    });

    refreshButton.addEventListener("click", refreshLibrary);
    refreshExtensionsButton.addEventListener("click", refreshExtensions);
    if ("serviceWorker" in navigator && window.isSecureContext) {
        navigator.serviceWorker.register("/stash-sw.js", { scope: "/" }).catch(() => {});
    }
    initialize();
})();
