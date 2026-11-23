const LOCAL_STASH_URL = "http" + "://" + "127.0.0.1" + ":5050";

const serverUrlInput = document.getElementById("serverUrl");
const pairingCodeInput = document.getElementById("pairingCode");
const pairingForm = document.getElementById("pairingForm");
const localPairingForm = document.getElementById("localPairingForm");
const localPairingCode = document.getElementById("localPairingCode");
const connectLocalButton = document.getElementById("connectLocalButton");
const connectButton = document.getElementById("connectButton");
const copyVideoButton = document.getElementById("copyVideoButton");
const disconnectButton = document.getElementById("disconnectButton");
const connectionLabel = document.getElementById("connectionLabel");
const contentConsent = document.getElementById("contentConsent");
const message = document.getElementById("message");
const localNote = document.getElementById("localNote");

function cleanServerUrl(value) {
    return String(value || "").trim().replace(/\/+$/, "");
}

function setMessage(text, kind = "ready") {
    message.textContent = text;
    message.dataset.kind = kind;
}

function simpleCopyError(error, code = "") {
    const reason = String(error || "").toLowerCase();
    const errorCode = String(code || "").toLowerCase();
    if (reason.includes("connect this extension") || reason.includes("browser connection expired")) {
        return "Connect the extension with a new one-time code in Stash Settings.";
    }
    if (errorCode === "video_copy_disabled") {
        return "Turn on video copying in Stash settings.";
    }
    if (errorCode === "video_too_large") {
        return "This video is too large to copy.";
    }
    if (reason.includes("stash itself") || reason.includes("video on its website")) {
        return "Open a video page first.";
    }
    if (reason.includes("no video")) {
        return "No video found. Play one first.";
    }
    if (reason.includes("not running") || reason.includes("could not connect")) {
        return "Open Stash, then try again.";
    }
    if (reason.includes("could not read this tab") || reason.includes("cannot be accessed") || reason.includes("reload the video page")) {
        return "Refresh the video page and try again.";
    }
    if (reason.includes("capture is paused") || reason.includes("capture is disabled")) {
        return "Copying is disabled in Stash settings.";
    }
    if (reason.includes("video copying is off") || reason.includes("video_copy_disabled")) {
        return "Turn on video copying in Stash settings.";
    }
    if (reason.includes("drm-protected playback")) {
        return "This video is protected and cannot be copied.";
    }
    if (reason.includes("video is not ready")) {
        return "Wait for the video to load, then try again.";
    }
    if (reason.includes("larger than stash's 2 gb upload limit")) {
        return "This video is too large to copy.";
    }
    if (reason.includes("no video track") || reason.includes("does not support video capture")) {
        return "This video cannot be copied in this browser.";
    }
    if (reason.includes("failed to fetch") || reason.includes("networkerror") || reason.includes("could not connect")) {
        return "Stash could not connect. Keep it open and try again.";
    }
    if (reason.includes("already running")) {
        return "A video is already copying. Wait a moment and try again.";
    }
    if (reason.includes("upload connection") || reason.includes("did not answer") || reason.includes("session expired")) {
        return "The copy stopped before finishing. Keep Stash open and try again.";
    }
    const shortReason = String(error || "")
        .replace(/^error:\s*/i, "")
        .replace(/\s*\(HTTP \d{3}\)/i, "")
        .trim();
    if (shortReason && shortReason.length <= 90 && !/^(failed to fetch|networkerror|typeerror|cannot read properties|uncaught)/i.test(shortReason)) {
        return shortReason;
    }
    return "Could not copy this video. Try another video.";
}

function isLocalStash(url) {
    return url.protocol === "http:" &&
        ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) &&
        url.port === "5050" &&
        ["", "/"].includes(url.pathname);
}

async function loadConnection() {
    try {
        const stored = await chrome.storage.local.get([
            "stashServerUrl",
            "stashAccessToken",
            "stashLocalAccessToken",
            "stashContentConsent"
        ]);
        const remoteConnected = Boolean(stored.stashServerUrl && stored.stashAccessToken);
        const localConnected = Boolean(stored.stashLocalAccessToken);
        disconnectButton.hidden = !remoteConnected;

        if (remoteConnected) {
            const host = new URL(stored.stashServerUrl).host;
            connectionLabel.textContent = `Remote Stash · ${host}`;
            localNote.textContent = "Saved to remote Stash.";
            if (stored.stashContentConsent !== true) {
                setMessage("Error · Reconnect in Advanced and confirm the remote destination.", "error");
                return;
            }
        } else if (localConnected) {
            connectionLabel.textContent = "Local Stash · this Mac";
            localNote.textContent = "Saved on this Mac.";
        } else {
            connectionLabel.textContent = "Local Stash · this Mac";
            localNote.textContent = "Connect in Stash Settings before copying videos.";
        }
        setMessage("Ready");
    } catch {
        setMessage("Error · Stash could not read the saved extension connection.", "error");
    }
}

copyVideoButton.addEventListener("click", async () => {
    copyVideoButton.disabled = true;
    setMessage("Copying…");
    try {
        const result = await chrome.runtime.sendMessage({ type: "COPY_ACTIVE_VIDEO" });
        if (!result?.success) {
            const error = new Error(result?.error || "Stash could not copy this video.");
            error.code = result?.code || "";
            throw error;
        }

        if (result.clipboard_published) {
            setMessage("Copied", "success");
        } else if (result.remote) {
            setMessage("Saved to remote Stash", "success");
        } else {
            setMessage("Saved, but not copied to clipboard", "error");
        }
    } catch (error) {
        setMessage(simpleCopyError(error?.message, error?.code), "error");
    } finally {
        copyVideoButton.disabled = false;
    }
});

localPairingForm.addEventListener("submit", async event => {
    event.preventDefault();
    const code = String(localPairingCode.value || "").trim();
    if (!code) {
        setMessage("Enter the one-time code from Stash Settings.", "error");
        return;
    }

    connectLocalButton.disabled = true;
    setMessage("Connecting to this Mac…");
    try {
        const response = await fetch(LOCAL_STASH_URL + "/api/auth/local-extension-pair", {
            method: "POST",
            credentials: "omit",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ code })
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || !result.accessToken) {
            throw new Error(result.error || "Stash could not connect this extension.");
        }

        await chrome.storage.local.set({
            stashServerUrl: LOCAL_STASH_URL,
            stashLocalAccessToken: result.accessToken,
            stashContentConsent: true
        });
        await chrome.storage.local.remove(["stashAccessToken"]);
        localPairingCode.value = "";
        connectionLabel.textContent = "Local Stash · this Mac";
        localNote.textContent = "Videos will be saved to this Mac.";
        setMessage("Connected. Try Copy video again.", "success");
    } catch (error) {
        setMessage(error?.message || "Stash could not connect this extension.", "error");
    } finally {
        connectLocalButton.disabled = false;
    }
});

pairingForm.addEventListener("submit", async event => {
    event.preventDefault();
    const serverUrl = cleanServerUrl(serverUrlInput.value);
    const code = pairingCodeInput.value.trim();
    let parsed;
    try {
        parsed = new URL(serverUrl);
        if (isLocalStash(parsed)) {
            throw new Error("Use Connect this Mac Stash above for this Mac.");
        }
        if (parsed.protocol !== "https:") throw new Error();
    } catch (error) {
        setMessage(error.message || "Enter a public HTTPS Stash address.", "error");
        return;
    }
    if (!code) {
        setMessage("Error · Paste a one-time pairing code from remote Stash Settings.", "error");
        return;
    }
    if (!contentConsent.checked) {
        setMessage("Error · Confirm that selected videos may be sent to this remote server.", "error");
        return;
    }

    connectButton.disabled = true;
    setMessage("Ready · Connecting remote Stash…");
    try {
        const allowed = await chrome.permissions.request({ origins: [`${parsed.origin}/*`] });
        if (!allowed) throw new Error("Chrome did not allow access to the remote Stash address.");

        const response = await fetch(serverUrl + "/api/shared/extensions/pair", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                code,
                label: "Chrome on " + navigator.platform
            })
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || !result.accessToken) {
            throw new Error(result.error || "Remote Stash could not connect this extension.");
        }

        await chrome.storage.local.set({
            stashServerUrl: serverUrl,
            stashAccessToken: result.accessToken,
            stashContentConsent: true
        });
        await chrome.storage.local.remove(["stashLocalAccessToken"]);
        pairingCodeInput.value = "";
        contentConsent.checked = false;
        connectionLabel.textContent = `Remote Stash · ${parsed.host}`;
        localNote.textContent = "Saved to remote Stash.";
        disconnectButton.hidden = false;
        setMessage("Ready · Remote Stash connected. Selected videos go to that server.");
    } catch (error) {
        setMessage(`Error · ${error?.message || "Remote Stash could not connect."}`, "error");
    } finally {
        connectButton.disabled = false;
    }
});

disconnectButton.addEventListener("click", async () => {
    await chrome.storage.local.remove([
        "stashServerUrl",
        "stashAccessToken",
        "stashLocalAccessToken",
        "stashContentConsent"
    ]);
    pairingCodeInput.value = "";
    contentConsent.checked = false;
    disconnectButton.hidden = true;
    connectionLabel.textContent = "Local Stash · this Mac";
    localNote.textContent = "Saved on this Mac.";
    setMessage("Ready");
});

loadConnection();
