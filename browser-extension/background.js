const LOCAL_COPY_MAKER_URL = "http" + "://" + "127.0.0.1" + ":5050";

const SHARED_ENDPOINTS = {
    browserCopy: "/api/shared/extensions/browser-copy",
    videoCaptureStart: "/api/shared/extensions/video-capture-start"
};
const MAX_VIDEO_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024;

function cleanServerUrl(value) {
    return String(value || "").trim().replace(/\/+$/, "");
}

function safeHeader(value, maxLength) {
    return String(value || "")
        .replace(/[\r\n\0]/g, " ")
        .replace(/[^\x20-\x7E]/g, "?")
        .slice(0, maxLength);
}

async function getStashConnection() {
    const stored = await chrome.storage.local.get([
        "stashServerUrl",
        "stashAccessToken",
        "stashLocalAccessToken"
    ]);
    const serverUrl = cleanServerUrl(stored.stashServerUrl);
    const accessToken = String(stored.stashAccessToken || "").trim();

    if (serverUrl && accessToken) {
        return {
            shared: true,
            serverUrl,
            accessToken
        };
    }

    const localAccessToken = String(stored.stashLocalAccessToken || "").trim();
    if (serverUrl && localAccessToken) {
        return {
            shared: false,
            serverUrl,
            accessToken: localAccessToken
        };
    }

    return {
        shared: false,
        serverUrl: LOCAL_COPY_MAKER_URL,
        accessToken: ""
    };
}

async function ensureContentScript(tabId) {
    try {
        const ready = await chrome.tabs.sendMessage(tabId, { type: "STASH_PING" });
        if (ready?.ready) return;
    } catch { }
    await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
}

async function getConnectedStash() {
    const stored = await chrome.storage.local.get([
        "stashServerUrl",
        "stashAccessToken",
        "stashLocalAccessToken",
        "stashContentConsent"
    ]);
    if (stored.stashServerUrl && stored.stashAccessToken) {
        if (stored.stashContentConsent !== true) {
            throw new Error("Open Advanced and reconnect remote Stash after confirming its destination.");
        }
        return { shared: true, serverUrl: cleanServerUrl(stored.stashServerUrl), accessToken: stored.stashAccessToken };
    }

    const localAccessToken = String(stored.stashLocalAccessToken || "").trim();
    if (localAccessToken && cleanServerUrl(stored.stashServerUrl) === LOCAL_COPY_MAKER_URL) {
        return { shared: false, serverUrl: LOCAL_COPY_MAKER_URL, accessToken: localAccessToken };
    }

    throw new Error("Connect this extension in Stash Settings: create a one-time code under ‘Connect a browser on this Mac’, then enter it in the extension menu.");
}

async function copyVideoFromActiveTab() {
    const connection = await getConnectedStash();
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !tab.url) throw new Error("Open a video website in the current tab first.");

    let pageUrl;
    try {
        pageUrl = new URL(tab.url);
    } catch {
        throw new Error("This tab is not a regular website. Open a video page and try again.");
    }
    if (!["http:", "https:"].includes(pageUrl.protocol)) {
        throw new Error("This browser page cannot be accessed. Open a video website and try again.");
    }
    if (["127.0.0.1", "localhost", "[::1]"].includes(pageUrl.hostname) && pageUrl.port === "5050") {
        throw new Error("Open the video on its website first; this is Stash itself.");
    }

    await ensureContentScript(tab.id);
    let result;
    try {
        result = await chrome.tabs.sendMessage(tab.id, { type: "COPY_VIDEO_NOW" });
    } catch {
        throw new Error("Stash could not read this tab. Reload the video page, then try again.");
    }
    if (!result?.success) {
        const error = new Error(result?.error || "No video could be copied from this page.");
        error.code = result?.code || "";
        throw error;
    }
    return { ...result, remote: connection.shared };
}

async function stashFetch(operation, options = {}) {
    let connection = await getStashConnection();
    const headers = { ...(options.headers || {}) };
    let path = "";

    if (!connection.accessToken) {
        connection = await getConnectedStash();
    }
    const consent = await chrome.storage.local.get(["stashContentConsent"]);
    if (connection.shared && consent.stashContentConsent !== true) {
        throw new Error("Reconnect in the Stash extension and confirm where chosen copies are sent.");
    }

    if (connection.shared) {
        path = SHARED_ENDPOINTS[operation];
        if (!path) {
            throw new Error("This action is only available when Stash is connected to this Mac.");
        }
        headers.Authorization = "Bearer " + connection.accessToken;
    } else {
        path = operation === "videoCaptureStart"
            ? "/api/video-capture-start"
            : operation === "audioImport"
                ? "/api/browser-copy/import-audio-download"
                : "/api/browser-copy";
        headers["X-Copy-Maker-Extension-Token"] = connection.accessToken;
    }

    const response = await fetch(connection.serverUrl + path, {
        ...options,
        headers
    });
    if (!connection.shared && response.status === 401) {
        const result = await response.clone().json().catch(() => ({}));
        if (result.error === "login_required") {
            throw new Error("The Stash browser connection expired. In Stash Settings, create a new one-time code and reconnect this extension.");
        }
    }
    return response;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {

    if (message?.type === "COPY_ACTIVE_VIDEO") {
        copyVideoFromActiveTab()
            .then(sendResponse)
            .catch(error => sendResponse({
                success: false,
                error: error?.message || "Stash could not copy the video.",
                code: error?.code || ""
            }));
        return true;
    }

    if (message?.type === "GET_VIDEO_CLIPBOARD_SNAPSHOT") {
        getStashConnection()
            .then(connection => {
                const metadata = connection.shared ? {} : (message.metadata || {});
                return stashFetch("videoCaptureStart", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(metadata)
                });
            })
            .then(async response => {
                const result = await response.json();

                if (!response.ok || !result.success) {
                    const error = new Error(
                        result.error || "Stash could not read the clipboard state."
                    );
                    error.code = result.code || "";
                    throw error;
                }

                console.log(
                    "📋 VIDEO SNAPSHOT RECEIVED:",
                    result.clipboard_change_count
                );

                sendResponse({
                    success: true,
                    clipboard_change_count: result.clipboard_change_count,
                    item_id: result.item_id ?? null
                });
            })
            .catch(error => {
                console.warn("Stash could not read the system clipboard state:", error);
                sendResponse({
                    success: false,
                    error: error.message,
                    code: error.code || ""
                });
            });

        return true;
    }

    if (message?.type === "UPDATE_VIDEO_COPY_STATUS") {
        getStashConnection()
            .then(connection => {
                if (connection.shared) {
                    return { success: true };
                }
                return stashFetch("videoCaptureStart", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        item_id: message.itemId,
                        status: message.status
                    })
                }).then(response => response.json());
            })
            .then(sendResponse)
            .catch(error => sendResponse({ success: false, error: error.message }));
        return true;
    }

    if (message?.type === "CANCEL_VIDEO_COPY") {
        getStashConnection()
            .then(connection => {
                if (connection.shared || message.itemId == null) {
                    return { success: true };
                }
                return stashFetch("videoCaptureStart", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ cancel_item_id: message.itemId })
                }).then(response => response.json());
            })
            .then(sendResponse)
            .catch(error => sendResponse({ success: false, error: error.message }));
        return true;
    }

    if (message?.type === "COPY_VIDEO_FROM_SOURCE") {
        (async () => {
            const metadata = message.metadata && typeof message.metadata === "object"
                ? message.metadata
                : {};
            const candidates = Array.isArray(message.candidates)
                ? message.candidates.slice(0, 5)
                : [];
            let lastSourceError = "No complete video file was found.";

            for (const candidate of candidates) {
                let sourceUrl;
                try {
                    sourceUrl = new URL(candidate);
                } catch {
                    continue;
                }
                if (!["http:", "https:"].includes(sourceUrl.protocol)) {
                    continue;
                }

                let sourceResponse;
                let videoBlob;
                try {
                    sourceResponse = await fetch(sourceUrl.href, {
                        credentials: "include",
                        cache: "no-store"
                    });
                    if (sourceResponse.status !== 200) {
                        lastSourceError = `The video source returned ${sourceResponse.status}.`;
                        continue;
                    }
                    videoBlob = await sourceResponse.blob();
                    if (!videoBlob.size) {
                        lastSourceError = "The video source was empty.";
                        continue;
                    }
                } catch (error) {
                    lastSourceError = error?.message || "The video source could not be downloaded.";
                    continue;
                }

                const itemId = metadata.itemId;
                try {
                    if (itemId != null) {
                        await stashFetch("videoCaptureStart", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ item_id: itemId, status: "saving" })
                        });
                    }
                    try {
                        if (sender?.tab?.id != null) {
                            chrome.tabs.sendMessage(sender.tab.id, {
                                type: "VIDEO_COPY_STAGE",
                                stage: "saving"
                            }).catch(() => {});
                        }
                    } catch { }

                    const sourceMimeType = (
                        videoBlob.type ||
                        sourceResponse.headers.get("content-type") ||
                        metadata.mimeType ||
                        "video/mp4"
                    ).split(";", 1)[0];
                    const uploadResponse = await stashFetch("browserCopy", {
                        method: "POST",
                        headers: {
                            "Content-Type": safeHeader(sourceMimeType, 120),
                            "X-Copy-Maker-Type": "video",
                            "X-Copy-Maker-URL": safeHeader(sourceUrl.href, 4000),
                            "X-Copy-Maker-Page": safeHeader(metadata.pageUrl, 4000),
                            "X-Copy-Maker-Title": safeHeader(metadata.title, 240),
                            "X-Copy-Maker-Direct-Source": "1",
                            "X-Copy-Maker-Expected-Duration": String(Number(metadata.duration) || ""),
                            ...(metadata.clipboardChangeCount !== null && metadata.clipboardChangeCount !== undefined
                                ? { "X-Copy-Maker-Clipboard-Change-Count": String(metadata.clipboardChangeCount) }
                                : {}),
                            ...(itemId != null ? { "X-Copy-Maker-Item-ID": String(itemId) } : {})
                        },
                        body: videoBlob
                    });
                    const result = await uploadResponse.json().catch(() => null);
                    if (uploadResponse.status === 422 && result?.code === "incomplete_video_source") {
                        lastSourceError = "The direct source was incomplete; Stash will capture the selected video instead.";
                        if (itemId != null) {
                            await stashFetch("videoCaptureStart", {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({ item_id: itemId, status: "downloading" })
                            }).catch(() => {});
                        }
                        continue;
                    }
                    if (!uploadResponse.ok || result?.success !== true) {
                        const statusSuffix = ` (HTTP ${uploadResponse.status})`;
                        const fallbackError = uploadResponse.status === 413
                            ? "This video is larger than Stash's 2 GB upload limit."
                            : uploadResponse.ok
                                ? "Stash returned an invalid response while saving the video."
                                : "Stash could not save the video.";
                        const error = new Error(`${result?.error || fallbackError}${uploadResponse.ok ? "" : statusSuffix}`);
                        error.code = result?.code || (uploadResponse.status === 413 ? "video_too_large" : "");
                        throw error;
                    }
                    sendResponse({ success: true, result, direct: true });
                    return;
                } catch (error) {
                    sendResponse({
                        success: false,
                        error: error?.message || "Stash could not save the downloaded video.",
                        code: error?.code || "",
                        fallback: false
                    });
                    return;
                }
            }

            sendResponse({ success: false, error: lastSourceError, fallback: true });
        })().catch(error => sendResponse({
            success: false,
            error: error?.message || "Direct video download failed.",
            fallback: true
        }));
        return true;
    }

    if (message?.type === "UPLOAD_CAPTURED_VIDEO") {
        const bytes = new Uint8Array(message.bytes || []);
        if (!bytes.byteLength) {
            sendResponse({ success: false, error: "The captured video was empty." });
            return false;
        }

        stashFetch("browserCopy", {
            method: "POST",
            headers: {
                "Content-Type": safeHeader(message.mimeType || "video/webm", 120),
                "X-Copy-Maker-Type": "video",
                "X-Copy-Maker-URL": safeHeader(message.url, 4000),
                "X-Copy-Maker-Page": safeHeader(message.pageUrl, 4000),
                "X-Copy-Maker-Title": safeHeader(message.title, 240),
                ...(message.clipboardChangeCount !== null
                    ? {
                        "X-Copy-Maker-Clipboard-Change-Count":
                            String(message.clipboardChangeCount)
                    }
                    : {})
            },
            body: bytes
        })
            .then(async response => {
                const result = await response.json().catch(() => ({}));
                if (!response.ok || !result.success) {
                    throw new Error(result.error || "Stash could not save the video.");
                }
                sendResponse(result);
            })
            .catch(error => {
                console.error("Stash could not upload the captured video:", error);
                sendResponse({ success: false, error: error.message });
            });

        return true;
    }

    return false;
});

chrome.runtime.onConnect.addListener(port => {
    if (port.name !== "stash-video-upload") {
        return;
    }

    let upload = null;

    function respond(requestId, result) {
        if (typeof requestId !== "string" || !requestId) {
            return;
        }
        try {
            port.postMessage({ requestId, ...result });
        } catch {
            // The content page may have closed the port while the upload was finishing.
        }
    }

    port.onMessage.addListener(async message => {
        const requestId = message?.requestId;

        try {
            if (message?.type === "start") {
                const totalBytes = Number(message.totalBytes);
                if (upload) {
                    throw new Error("A Stash video upload is already in progress.");
                }
                if (
                    !Number.isSafeInteger(totalBytes) ||
                    totalBytes <= 0 ||
                    totalBytes > MAX_VIDEO_UPLOAD_BYTES
                ) {
                    throw new Error("This video is empty or larger than Stash's 2 GB upload limit.");
                }

                const metadata = message.metadata && typeof message.metadata === "object"
                    ? message.metadata
                    : {};
                const requestedMimeType = String(metadata.mimeType || "video/webm")
                    .split(";", 1)[0]
                    .trim()
                    .toLowerCase();
                const mimeType = /^[a-z0-9!#$&^_.+-]+\/[a-z0-9!#$&^_.+-]+$/.test(requestedMimeType)
                    ? requestedMimeType
                    : "video/webm";
                upload = {
                    totalBytes,
                    receivedBytes: 0,
                    chunks: [],
                    metadata: {
                        mimeType,
                        url: safeHeader(metadata.url, 4000),
                        pageUrl: safeHeader(metadata.pageUrl, 4000),
                        title: safeHeader(metadata.title, 240),
                        clipboardChangeCount: metadata.clipboardChangeCount,
                        itemId: metadata.itemId
                    }
                };

                respond(requestId, { success: true, receivedBytes: 0 });
                return;
            }

            if (!upload) {
                throw new Error("The Stash video upload session expired. Please try copying again.");
            }

            if (message?.type === "chunk") {
                const offset = Number(message.offset);
                if (!Number.isSafeInteger(offset) || offset !== upload.receivedBytes) {
                    throw new Error("Stash received video data out of order. Please try copying again.");
                }
                if (typeof message.data !== "string" || !message.data) {
                    throw new Error("Stash received an empty video section.");
                }

                const binary = atob(message.data);
                const bytes = new Uint8Array(binary.length);
                for (let index = 0; index < binary.length; index += 1) {
                    bytes[index] = binary.charCodeAt(index);
                }

                if (!bytes.byteLength || upload.receivedBytes + bytes.byteLength > upload.totalBytes) {
                    throw new Error("Stash received invalid video data. Please try copying again.");
                }

                upload.chunks.push(bytes);
                upload.receivedBytes += bytes.byteLength;
                respond(requestId, { success: true, receivedBytes: upload.receivedBytes });
                return;
            }

            if (message?.type !== "finish") {
                throw new Error("Stash received an unknown video upload step.");
            }
            if (upload.receivedBytes !== upload.totalBytes) {
                throw new Error("Stash did not receive the full video. Please try copying again.");
            }

            const completed = upload;
            upload = null;
            const videoBlob = new Blob(completed.chunks, {
                type: completed.metadata.mimeType
            });
            const metadata = completed.metadata;
            const response = await stashFetch("browserCopy", {
                method: "POST",
                headers: {
                    "Content-Type": metadata.mimeType,
                    "X-Copy-Maker-Type": "video",
                    "X-Copy-Maker-URL": metadata.url,
                    "X-Copy-Maker-Page": metadata.pageUrl,
                        "X-Copy-Maker-Title": metadata.title,
                    ...(metadata.itemId != null
                        ? { "X-Copy-Maker-Item-ID": String(metadata.itemId) }
                        : {}),
                    ...(metadata.clipboardChangeCount !== null && metadata.clipboardChangeCount !== undefined
                        ? {
                            "X-Copy-Maker-Clipboard-Change-Count":
                                String(metadata.clipboardChangeCount)
                        }
                        : {})
                },
                body: videoBlob
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok || result?.success !== true) {
                throw new Error(result?.error || "Stash could not save the video.");
            }

            respond(requestId, result);
        } catch (error) {
            upload = null;
            respond(requestId, {
                success: false,
                error: error?.message || "Stash could not save the video."
            });
        }
    });

    port.onDisconnect.addListener(() => {
        upload = null;
    });
});


// ==========================================
// CREATE UNIVERSAL CONTEXT MENU
// ==========================================

chrome.runtime.onInstalled.addListener(() => {

    chrome.contextMenus.create({
        id: "copy-maker",
        title: "⚡ Copy with Stash",
        contexts: ["all"]
    });

    chrome.contextMenus.create({
        id: "copy-maker-audio",
        title: "🎵 Copy audio to Stash",
        contexts: ["link", "audio", "page"]
    });

});


// ==========================================
// HANDLE STASH CLICK
// ==========================================

chrome.contextMenus.onClicked.addListener(
    async (info, tab) => {

        if (info.menuItemId === "copy-maker-audio") {

            let audioUrl = info.linkUrl || info.srcUrl || "";

            if (!audioUrl && tab?.id) {
                try {
                    await ensureContentScript(tab.id);
                    const detected = await chrome.tabs.sendMessage(
                        tab.id,
                        { type: "GET_AUDIO_CONTEXT" }
                    );
                    audioUrl = detected?.url || "";
                } catch (error) {
                    console.warn("Page audio detection failed:", error);
                }
            }

            if (!audioUrl) {
                console.error(
                    "Stash could not find a direct audio URL. " +
                    "The page may use a protected or hidden audio stream."
                );
                return;
            }

            let parsedUrl;

            try {
                parsedUrl = new URL(audioUrl);

                if (!["http:", "https:"].includes(parsedUrl.protocol)) {
                    throw new Error("Only HTTP/HTTPS audio URLs are supported.");
                }
            } catch (error) {
                console.error("Invalid audio URL:", error);
                return;
            }

            try {
                // First attempt: send audio directly to Stash.
                const sourceResponse = await fetch(parsedUrl.href);

                if (!sourceResponse.ok) {
                    throw new Error(
                        "Source server returned HTTP " + sourceResponse.status
                    );
                }

                const audioBlob = await sourceResponse.blob();

                if (!audioBlob.size) {
                    throw new Error("The audio response was empty.");
                }

                const contentType =
                    audioBlob.type || "application/octet-stream";

                const uploadResponse = await stashFetch(
                    "browserCopy",
                    {
                        method: "POST",
                        headers: {
                            "Content-Type": safeHeader(contentType, 120),
                            "X-Copy-Maker-Type": "audio",
                            "X-Copy-Maker-URL": safeHeader(parsedUrl.href, 4000),
                            "X-Copy-Maker-Page": safeHeader(info.pageUrl || tab?.url, 4000),
                            "X-Copy-Maker-Title": safeHeader(parsedUrl.hostname, 240)
                        },
                        body: audioBlob
                    }
                );

                const result = await uploadResponse.json();

                if (!uploadResponse.ok || !result.success) {
                    throw new Error(
                        result.error || "Direct audio upload failed."
                    );
                }

                console.log(
                    "Stash audio saved:",
                    result.item?.original_name || result.message
                );

            } catch (directError) {
                // Fallback: preserve the existing download-and-import pipeline.
                console.warn(
                    "Direct audio copy failed; trying download fallback:",
                    directError
                );

                try {
                    const downloadId = await chrome.downloads.download({
                        url: parsedUrl.href,
                        saveAs: false
                    });

                    console.log(
                        "Stash audio download started:",
                        downloadId
                    );
                } catch (downloadError) {
                    console.error(
                        "Both audio-copy methods failed:",
                        downloadError
                    );
                }
            }

            return;
        }

        if (info.menuItemId !== "copy-maker") {
            return;
        }

        if (!tab || !tab.id) {
            console.log("No active tab.");
            return;
        }

        try {

            await ensureContentScript(tab.id);

            const context =
                await chrome.tabs.sendMessage(
                    tab.id,
                    {
                        type: "GET_CONTEXT"
                    }
                );

            console.log(
                "Stash context:",
                context
            );


            // =================================
            // VIDEO
            // =================================

            if (context.type === "video") {

                console.log(
                    "🎥 Stash: VIDEO detected."
                );

                let clipboardChangeCount = null;
                console.log("📋 VIDEO SNAPSHOT: starting request");

                try {
                    const startResponse = await stashFetch(
                        "videoCaptureStart",
                        {
                            method: "POST",
                            headers: {}
                        }
                    );

                    const startResult = await startResponse.json();

                    if (startResponse.ok && startResult.success) {
                        clipboardChangeCount =
                            startResult.clipboard_change_count;
                        console.log(
                            "📋 VIDEO SNAPSHOT RECEIVED:",
                            clipboardChangeCount
                        );
                    } else {
                        console.warn(
                            "Stash could not track the system clipboard; " +
                            "the video will still be saved to the library."
                        );
                    }
                } catch (error) {
                    console.warn(
                        "Stash could not read the system clipboard state:",
                        error
                    );
                }

                const capture =
                    await chrome.tabs.sendMessage(
                        tab.id,
                        {
                            type: "CAPTURE_VIDEO"
                        }
                    );

                if (!capture || !capture.success) {

                    console.error(
                        "❌ Video capture failed:",
                        capture?.error
                    );

                    return;
                }

                console.log(
                    "🎥 Video captured:",
                    capture.size,
                    "bytes"
                );


                const videoBytes = new Uint8Array(capture.bytes);
                console.log(
                    "📋 VIDEO SNAPSHOT BEFORE UPLOAD:",
                    clipboardChangeCount
                );

                const response = await stashFetch(
                    "browserCopy",
                    {
                        method: "POST",

                        headers: {
                            "Content-Type":
                                safeHeader(capture.mimeType || "video/webm", 120),

                            "X-Copy-Maker-Type":
                                "video",

                            "X-Copy-Maker-URL":
                                safeHeader(context.url, 4000),

                            "X-Copy-Maker-Page":
                                safeHeader(tab.url, 4000),

                            "X-Copy-Maker-Title":
                                safeHeader(tab.title, 240),

                            ...(clipboardChangeCount !== null
                                ? {
                                    "X-Copy-Maker-Clipboard-Change-Count":
                                        String(clipboardChangeCount)
                                }
                                : {})
                        },

                        body: videoBytes
                    }
                );


                const result =
                    await response.json();

                console.log(
                    "🎥 Stash video response:",
                    result
                );

                if (result.clipboard_published) {
                    console.log(
                        "📋 Video is ready to paste with Cmd+V."
                    );
                } else {
                    console.warn(
                        "📋 Video was saved to the library, but the " +
                        "system clipboard changed or was unavailable."
                    );
                }

                return;
            }


            // =================================
            // TEXT / IMAGE / AUDIO / LINK
            // =================================

            const response = await stashFetch(
                "browserCopy",
                {
                    method: "POST",

                    headers: {
                        "Content-Type": "application/json"
                    },

                    body: JSON.stringify({

                        type: context.type,

                        url: context.url,

                        text: context.text,

                        page_url:
                            tab.url || "",

                        title:
                            tab.title || ""

                    })
                }
            );


            const result =
                await response.json();

            console.log(
                "Stash response:",
                result
            );

        } catch (error) {

            console.error(
                "❌ Stash error:",
                error
            );

        }

    }
);


// ==========================================
// IMPORT COMPLETED AUDIO DOWNLOADS
// ==========================================

const AUDIO_DOWNLOAD_EXTENSIONS = new Set([
    ".aac",
    ".aif",
    ".aiff",
    ".amr",
    ".flac",
    ".m4a",
    ".mid",
    ".midi",
    ".mp2",
    ".mp3",
    ".mpga",
    ".oga",
    ".ogg",
    ".opus",
    ".wav",
    ".wma"
]);


function isAudioDownload(downloadItem) {

    const mimeType = String(downloadItem.mime || "")
        .split(";", 1)[0]
        .trim()
        .toLowerCase();
    const filename = String(downloadItem.filename || "")
        .split(/[?#]/, 1)[0];
    const extension = (filename.match(/\.[^./\\]+$/) || [""])[0]
        .toLowerCase();

    return mimeType.startsWith("audio/") ||
        AUDIO_DOWNLOAD_EXTENSIONS.has(extension);
}


async function importCompletedAudioDownload(downloadId) {

    try {
        const connection = await getStashConnection();
        if (connection.shared) {
            // A public Stash server cannot safely receive a filename from a
            // person's Downloads folder. Direct audio uploads still work.
            return;
        }

        const [downloadItem] = await chrome.downloads.search({
            id: downloadId
        });

        if (
            !downloadItem ||
            downloadItem.state !== "complete" ||
            downloadItem.exists === false ||
            !downloadItem.filename ||
            !isAudioDownload(downloadItem)
        ) {
            return;
        }

        const response = await stashFetch(
            "audioImport",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    download_id: downloadItem.id,
                    filename: downloadItem.filename,
                    mime_type: downloadItem.mime || "",
                    url: downloadItem.finalUrl || downloadItem.url || "",
                    page_url: downloadItem.referrer || ""
                })
            }
        );

        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(
                result.error || "Audio import failed."
            );
        }

        console.log(
            "Stash audio download imported:",
            result.item?.original_name || downloadItem.filename
        );

    } catch (error) {

        console.error(
            "Stash could not import the audio download:",
            error
        );
    }
}


chrome.downloads.onChanged.addListener(delta => {

    if (delta.state?.current === "complete") {
        importCompletedAudioDownload(delta.id);
    }
});
