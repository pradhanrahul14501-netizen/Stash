(() => {
    "use strict";

    // Do not add a Copy with Stash button over a video inside Stash itself.
    // That control is an extension overlay, so it must never become a visible
    // mark on saved video previews.
    let isStashLibraryPage = (
        window.location.protocol === "file:" ||
        (
            ["127.0.0.1", "localhost", "[::1]"].includes(window.location.hostname) &&
            window.location.port === "5050"
        )
    );
    if (isStashLibraryPage) {
        return;
    }

    let selectedVideo = null;
    let isCapturing = false;
    let copyJobActive = false;
    let copyButton = null;
    let lastPointerPosition = null;
    let selectionRefreshQueued = false;

    // A paired extension may point at any public Stash address. Resolve that
    // address after the content script loads and remove a button immediately
    // if this is the user's own Stash library.
    chrome.storage?.local?.get(["stashServerUrl"])
        .then(({ stashServerUrl }) => {
            if (!stashServerUrl) {
                return;
            }
            try {
                isStashLibraryPage = new URL(stashServerUrl).origin === window.location.origin;
                if (isStashLibraryPage && copyButton) {
                    copyButton.remove();
                    copyButton = null;
                }
            } catch {
                // Ignore an invalid saved address. Pairing validates it.
            }
        })
        .catch(() => {});

    // =========================================================
    // ACTIVE CAPTURE CONTROL
    // =========================================================

    let activeRecorder = null;
    let activeStream = null;
    let captureGeneration = 0;

    // =========================================================
    // VIDEO SELECTION
    // =========================================================

    function selectVideo(video) {
        if (!video || video.tagName !== "VIDEO") {
            return;
        }

        // Same video: do nothing.
        if (selectedVideo === video) {
            return;
        }

        // A new video means the previous capture is no longer valid.
        if (selectedVideo && selectedVideo !== video) {
            console.log("🔄 STASH VIDEO CHANGED");
            console.log("🛑 Invalidating previous capture...");

            captureGeneration++;

            if (
                activeRecorder &&
                activeRecorder.state !== "inactive"
            ) {
                try {
                    activeRecorder.stop();
                } catch (error) {
                    console.log(
                        "Recorder already stopping:",
                        error.message
                    );
                }
            }

            if (activeStream) {
                activeStream
                    .getTracks()
                    .forEach(track => track.stop());

                activeStream = null;
            }

            activeRecorder = null;
            isCapturing = false;

            console.log("✅ Previous capture reset.");
        }

        selectedVideo = video;

        console.log("🎥 STASH VIDEO SELECTED");
        console.log("src:", video.currentSrc || video.src);
        console.log("readyState:", video.readyState);
        console.log("duration:", video.duration);
    }

    function videoFromElement(element) {
        if (!element) {
            return null;
        }

        if (element?.tagName === "VIDEO") {
            return element;
        }

        if (element?.closest) {
            const video = element.closest("video");
            if (video) {
                return video;
            }
        }

        // Pinterest often puts a clickable layer around a video. Check the
        // layer's contents before falling back to the page-wide search.
        if (element?.querySelector) {
            const video = element.querySelector("video");
            if (video) {
                return video;
            }
        }

        return null;
    }

    function getVideoAtPoint(clientX, clientY) {
        if (!Number.isFinite(clientX) || !Number.isFinite(clientY)) {
            return null;
        }

        // Check the visible stacked elements first. This finds a video even
        // when a site's button, image, or overlay receives the pointer event.
        for (const element of document.elementsFromPoint(clientX, clientY)) {
            const video = videoFromElement(element);
            if (video) {
                return video;
            }
        }

        const videos = document.querySelectorAll("video");

        for (const video of videos) {
            const rect = video.getBoundingClientRect();

            if (
                rect.width > 0 &&
                rect.height > 0 &&
                clientX >= rect.left &&
                clientX <= rect.right &&
                clientY >= rect.top &&
                clientY <= rect.bottom
            ) {
                return video;
            }
        }

        return null;
    }

    function getVideoFromEvent(event) {
        return (
            getVideoAtPoint(event.clientX, event.clientY) ||
            videoFromElement(event.target)
        );
    }

    function selectVideoAtPointer() {
        if (!lastPointerPosition) {
            return;
        }

        const video = getVideoAtPoint(
            lastPointerPosition.clientX,
            lastPointerPosition.clientY
        );

        if (video) {
            selectVideo(video);
            showCopyButton(video);
        }
    }

    function scheduleVideoSelectionRefresh() {
        if (selectionRefreshQueued) {
            return;
        }

        selectionRefreshQueued = true;

        requestAnimationFrame(() => {
            selectionRefreshQueued = false;
            selectVideoAtPointer();
        });
    }

    function findVideoForCopy() {
        if (selectedVideo?.isConnected) {
            const rect = selectedVideo.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) return selectedVideo;
        }
        if (lastPointerPosition) {
            const pointed = getVideoAtPoint(lastPointerPosition.clientX, lastPointerPosition.clientY);
            if (pointed) return pointed;
        }

        const visibleVideos = [...document.querySelectorAll("video")]
            .map(video => ({ video, rect: video.getBoundingClientRect() }))
            .filter(({ video, rect }) => {
                const style = getComputedStyle(video);
                return rect.width > 80 && rect.height > 80
                    && style.display !== "none"
                    && style.visibility !== "hidden"
                    && Number(style.opacity || 1) > 0;
            });
        if (!visibleVideos.length) return null;

        const playing = visibleVideos.filter(({ video }) => !video.paused && !video.ended);
        return (playing.length ? playing : visibleVideos)
            .sort((a, b) => (b.rect.width * b.rect.height) - (a.rect.width * a.rect.height))[0].video;
    }

    // =========================================================
    // TRACK VIDEO
    // =========================================================

    document.addEventListener(
        "mouseover",
        event => {
            lastPointerPosition = {
                clientX: event.clientX,
                clientY: event.clientY
            };

            const video = getVideoFromEvent(event);

            if (video) {
                selectVideo(video);
                showCopyButton(video);
            }
        },
        true
    );

    // Pinterest and other feed-based sites can insert the real <video> only
    // after the pointer has already entered its card. Track pointer movement
    // and re-check after DOM changes so the Stash button still appears.
    document.addEventListener(
        "pointermove",
        event => {
            lastPointerPosition = {
                clientX: event.clientX,
                clientY: event.clientY
            };
            scheduleVideoSelectionRefresh();
        },
        true
    );

    const videoDiscoveryObserver = new MutationObserver(mutations => {
        const revealedVideo = mutations.some(mutation => {
            if (mutation.target?.closest?.("video")) {
                return true;
            }

            return [...mutation.addedNodes].some(node => {
                return (
                    node.nodeType === Node.ELEMENT_NODE &&
                    (
                        node.tagName === "VIDEO" ||
                        node.querySelector?.("video")
                    )
                );
            });
        });

        if (revealedVideo) {
            scheduleVideoSelectionRefresh();
        }
    });

    videoDiscoveryObserver.observe(document.documentElement, {
        childList: true,
        subtree: true
    });

    document.addEventListener(
        "contextmenu",
        event => {
            const video = getVideoFromEvent(event);

            if (video) {
                selectVideo(video);
            }
        },
        true
    );

    // =========================================================
    // CAPTURE VIDEO
    // =========================================================

    // =========================================================
    // FAST DIRECT VIDEO SOURCE
    // =========================================================

    function findDirectVideoSourceCandidates(video) {
        const activeSource = video.currentSrc || video.src || "";

        // Feed players expose a blob-backed MediaSource, not one complete
        // file. Nearby .mp4 requests may be fragments or belong to another
        // item, so capture the selected video element instead.
        if (/^(blob:|mediasource:)/i.test(activeSource)) {
            return [];
        }

        try {
            const parsed = new URL(activeSource, window.location.href);
            if (
                ["http:", "https:"].includes(parsed.protocol) &&
                /\.(mp4|m4v|mov|webm)$/i.test(parsed.pathname)
            ) {
                return [parsed.href];
            }
        } catch (_error) {
            return [];
        }

        return [];
    }

    async function tryDirectVideo(video, metadata) {
        if (video?.mediaKeys) {
            throw new Error("Stash cannot capture DRM-protected playback. Use an official download or export option instead.");
        }
        const candidates = findDirectVideoSourceCandidates(video);
        if (!candidates.length) {
            return null;
        }

        const result = await chrome.runtime.sendMessage({
            type: "COPY_VIDEO_FROM_SOURCE",
            candidates,
            metadata: {
                itemId: metadata.itemId,
                clipboardChangeCount: metadata.clipboardChangeCount,
                duration: video.duration,
                mimeType: "",
                pageUrl: window.location.href,
                title: document.title
            }
        });

        if (result?.success && result.result) {
            console.log("⚡ Original video saved directly to Stash.");
            return result.result;
        }
        if (result?.fallback) {
            console.log("⏩ Direct source unavailable; using playback capture:", result.error || "");
            return null;
        }

        const error = new Error(result?.error || "Stash could not save the video.");
        error.code = result?.code || "";
        throw error;
    }

    async function captureVideo(video) {
        if (!video) {
            throw new Error("No video selected.");
        }

        if (video.mediaKeys) {
            throw new Error("Stash cannot capture DRM-protected playback. Use an official download or export option instead.");
        }

        if (isCapturing) {
            throw new Error("Video capture already running.");
        }

        isCapturing = true;

        console.log("");
        console.log("===============================");
        console.log("🎥 STASH CAPTURE START");
        console.log("===============================");

        let stream = null;
        let recorder = null;
        let endedHandler = null;
        let emptyCheckTimer = null;

        const originalTime = video.currentTime;
        const originalRate = video.playbackRate;
        const originalPaused = video.paused;

        try {
            if (video.readyState < 2) {
                throw new Error("Video is not ready.");
            }

            if (typeof video.captureStream !== "function") {
                throw new Error(
                    "This browser does not support video capture."
                );
            }

            console.log("🎬 Duration:", video.duration);
            console.log(
                "⏱ Copy starting at:",
                video.currentTime
            );

            /*
             * Keep the current playback position.
             * Stash no longer jumps the video back to 0:00.
             */

            stream = video.captureStream();

            const videoTracks = stream.getVideoTracks();
            const audioTracks = stream.getAudioTracks();

            console.log(
                "🎥 video tracks:",
                videoTracks.length
            );

            console.log(
                "🔊 audio tracks:",
                audioTracks.length
            );

            if (!videoTracks.length) {
                throw new Error(
                    "No video track available."
                );
            }

            // -------------------------------------------------
            // MIME TYPE
            // -------------------------------------------------

            const formats = [
                "video/webm;codecs=vp9,opus",
                "video/webm;codecs=vp8,opus",
                "video/webm"
            ];

            let mimeType = "";

            for (const type of formats) {
                if (MediaRecorder.isTypeSupported(type)) {
                    mimeType = type;
                    break;
                }
            }

            if (!mimeType) {
                throw new Error(
                    "No supported MediaRecorder format."
                );
            }

            console.log("🎬 MIME:", mimeType);

            // -------------------------------------------------
            // RECORDER
            // -------------------------------------------------

            recorder = new MediaRecorder(
                stream,
                {
                    mimeType,
                    videoBitsPerSecond: 1500000
                }
            );

            const chunks = [];

            recorder.ondataavailable = event => {
                console.log(
                    "📦 dataavailable:",
                    event.data.size,
                    "bytes"
                );

                if (event.data && event.data.size > 0) {
                    chunks.push(event.data);
                }
            };

            const stopped = new Promise(
                (resolve, reject) => {

                    recorder.onerror = event => {
                        console.error(
                            "❌ MediaRecorder error:",
                            event
                        );

                        reject(
                            new Error(
                                "MediaRecorder failed."
                            )
                        );
                    };

                    recorder.onstop = () => {
                        console.log(
                            "🛑 Recorder stopped"
                        );

                        resolve();
                    };
                }
            );

            // -------------------------------------------------
            // START
            // -------------------------------------------------

            recorder.start(1000);

            console.log(
                "▶️ Recording started from:",
                video.currentTime
            );

            /*
             * Start playback only if necessary.
             *
             * If the video was already playing, keep it playing.
             * If it was paused, we need playback so captureStream()
             * can actually produce frames.
             */
            if (video.paused) {
                await video.play().catch(error => {
                    throw new Error(
                        "Could not start video playback: " +
                        error.message
                    );
                });
            }

            // -------------------------------------------------
            // STOP WHEN SOURCE VIDEO REALLY ENDS
            // -------------------------------------------------

            let finished = false;
            let endWatchTimer = null;

            const finish = () => {
                if (finished) {
                    return;
                }

                finished = true;

                if (endWatchTimer) {
                    clearInterval(endWatchTimer);
                    endWatchTimer = null;
                }

                console.log(
                    "🛑 STASH: stopping capture"
                );

                if (
                    recorder &&
                    recorder.state !== "inactive"
                ) {
                    recorder.stop();
                }
            };

            endedHandler = () => {
                console.log(
                    "🏁 Source video ended"
                );

                finish();
            };

            video.addEventListener(
                "ended",
                endedHandler,
                { once: true }
            );

            // -------------------------------------------------
            // END-OF-VIDEO WATCHDOG
            // -------------------------------------------------
            // YouTube may not always fire "ended" reliably.
            // Check the actual playback position as a fallback.

            endWatchTimer = setInterval(() => {
                if (
                    !video.duration ||
                    !Number.isFinite(video.duration)
                ) {
                    return;
                }

                const remaining =
                    video.duration - video.currentTime;

                if (remaining <= 0.25) {
                    console.log(
                        "🏁 Video reached its duration:",
                        video.currentTime,
                        "/",
                        video.duration
                    );

                    finish();
                }
            }, 250);

            // -------------------------------------------------
            // EARLY EMPTY-CAPTURE CHECK
            // -------------------------------------------------

            /*
             * Some browsers delay MediaRecorder's dataavailable
             * events. Do not stop a still-playing video just because
             * the first chunk has not arrived within four seconds.
             * The source-ended handler remains responsible for
             * completing the recording.
             */
            emptyCheckTimer = setTimeout(() => {

                if (
                    chunks.length === 0 &&
                    recorder &&
                    recorder.state !== "inactive"
                ) {
                    console.warn(
                        "⚠️ No capture data after 4 seconds; " +
                        "continuing until the video ends.",
                        {
                            currentTime: video.currentTime,
                            paused: video.paused,
                            videoTrackState: videoTracks[0]?.readyState,
                            videoTrackMuted: videoTracks[0]?.muted
                        }
                    );
                }

            }, 4000);

            await stopped;

            if (emptyCheckTimer) {
                clearTimeout(emptyCheckTimer);
            }

            if (endWatchTimer) {
                clearInterval(endWatchTimer);
                endWatchTimer = null;
            }

            if (endedHandler) {
                video.removeEventListener(
                    "ended",
                    endedHandler
                );
            }

            // -------------------------------------------------
            // STOP TRACKS
            // -------------------------------------------------

            if (stream) {
                stream.getTracks().forEach(
                    track => track.stop()
                );
            }

            // -------------------------------------------------
            // BUILD FILE
            // -------------------------------------------------

            const blob = new Blob(
                chunks,
                {
                    type: mimeType
                }
            );

            console.log(
                "📦 final video:",
                blob.size,
                "bytes"
            );

            if (blob.size === 0) {
                throw new Error(
                    "YouTube capture produced 0 bytes. " +
                    "The browser did not expose the video stream."
                );
            }

            return blob;

        } finally {

            if (emptyCheckTimer) {
                clearTimeout(emptyCheckTimer);
            }

            if (endedHandler) {
                video.removeEventListener(
                    "ended",
                    endedHandler
                );
            }

            if (stream) {
                stream.getTracks().forEach(
                    track => track.stop()
                );
            }

            /*
             * Restore the YouTube video exactly as the user
             * had it before pressing Copy.
             */
            try {
                video.currentTime = originalTime;
                video.playbackRate = originalRate;

                if (originalPaused) {
                    video.pause();
                }
            } catch (error) {
                console.log(
                    "⚠️ Could not fully restore video state:",
                    error.message
                );
            }

            isCapturing = false;
        }
    }

    // =========================================================
    // UPLOAD
    // =========================================================

    async function getClipboardSnapshotBeforeCapture(video) {
        try {
            const result = await chrome.runtime.sendMessage({
                type: "GET_VIDEO_CLIPBOARD_SNAPSHOT",
                metadata: {
                    create_pending: true,
                    title: document.title || "Video copy",
                    url: video?.currentSrc || video?.src || "",
                    page_url: window.location.href,
                    mime_type: video?.type || "",
                }
            });
            const changeCount = result?.clipboard_change_count;

            if (!result?.success) {
                const error = new Error(result?.error || "Clipboard snapshot was unavailable.");
                error.code = result?.code || "";
                throw error;
            }

            return {
                clipboardChangeCount: changeCount === undefined || changeCount === null
                    ? null
                    : String(changeCount),
                itemId: result.item_id ?? null
            };
        } catch (error) {
            if (error.code === "video_copy_disabled") {
                throw error;
            }
            console.warn(
                "⚠️ Could not record the clipboard before video capture:",
                error.message
            );
            return { clipboardChangeCount: null, itemId: null };
        }
    }

    async function updateVideoCopyStatus(itemId, status) {
        if (itemId == null) {
            return;
        }
        try {
            await chrome.runtime.sendMessage({
                type: "UPDATE_VIDEO_COPY_STATUS",
                itemId,
                status
            });
        } catch (error) {
            console.warn("Stash could not update the video status:", error.message);
        }
    }

    async function cancelPendingVideo(itemId) {
        if (itemId == null) {
            return;
        }
        try {
            await chrome.runtime.sendMessage({ type: "CANCEL_VIDEO_COPY", itemId });
        } catch (error) {
            console.warn("Stash could not clear the pending video:", error.message);
        }
    }

    const VIDEO_UPLOAD_CHUNK_BYTES = 1024 * 1024;
    const VIDEO_UPLOAD_RESPONSE_TIMEOUT_MS = 10 * 60 * 1000;

    function encodeVideoChunk(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = "";
        const encodingChunkSize = 0x8000;

        for (let offset = 0; offset < bytes.length; offset += encodingChunkSize) {
            binary += String.fromCharCode(
                ...bytes.subarray(offset, offset + encodingChunkSize)
            );
        }

        return btoa(binary);
    }

    function createVideoUploadChannel() {
        const port = chrome.runtime.connect({ name: "stash-video-upload" });
        const pending = new Map();
        let requestNumber = 0;
        let disconnected = false;

        function rejectPending(error) {
            for (const request of pending.values()) {
                clearTimeout(request.timer);
                request.reject(error);
            }
            pending.clear();
        }

        port.onMessage.addListener(response => {
            if (!response || typeof response.requestId !== "string") {
                return;
            }

            const request = pending.get(response.requestId);
            if (!request) {
                return;
            }

            clearTimeout(request.timer);
            pending.delete(response.requestId);

            if (response.success === true) {
                request.resolve(response);
            } else {
                request.reject(new Error(
                    response.error || "Stash could not upload the video."
                ));
            }
        });

        port.onDisconnect.addListener(() => {
            disconnected = true;
            const message = chrome.runtime.lastError?.message ||
                "Stash closed the video upload connection. Reload the Stash extension and try again.";
            rejectPending(new Error(message));
        });

        return {
            send(payload) {
                if (disconnected) {
                    return Promise.reject(new Error(
                        "Stash closed the video upload connection. Reload the Stash extension and try again."
                    ));
                }

                const requestId = `video-${++requestNumber}`;
                return new Promise((resolve, reject) => {
                    const timer = setTimeout(() => {
                        pending.delete(requestId);
                        reject(new Error(
                            "Stash did not answer the video upload. Keep Stash running and retry."
                        ));
                    }, VIDEO_UPLOAD_RESPONSE_TIMEOUT_MS);

                    pending.set(requestId, { resolve, reject, timer });

                    try {
                        port.postMessage({ ...payload, requestId });
                    } catch (error) {
                        clearTimeout(timer);
                        pending.delete(requestId);
                        reject(error);
                    }
                });
            },

            close() {
                if (!disconnected) {
                    disconnected = true;
                    port.disconnect();
                }
            }
        };
    }

    async function uploadVideo(
        blob,
        video,
        clipboardChangeCount,
        itemId
    ) {
        if (!blob || !Number.isFinite(blob.size) || blob.size <= 0) {
            throw new Error("The captured video is empty.");
        }

        const maximumBytes = 2 * 1024 * 1024 * 1024;
        if (blob.size > maximumBytes) {
            throw new Error("This video is larger than Stash's 2 GB upload limit.");
        }

        console.log(
            "☁️ Uploading video directly...",
            blob.size,
            "bytes"
        );

        const channel = createVideoUploadChannel();
        const mimeType = blob.type || "video/webm";

        try {
            await channel.send({
                type: "start",
                totalBytes: blob.size,
                metadata: {
                    mimeType,
                    url: video.currentSrc || video.src || "",
                    pageUrl: window.location.href,
                    title: document.title,
                    clipboardChangeCount,
                    itemId
                }
            });

            for (let offset = 0; offset < blob.size; offset += VIDEO_UPLOAD_CHUNK_BYTES) {
                const end = Math.min(offset + VIDEO_UPLOAD_CHUNK_BYTES, blob.size);
                const chunk = await blob.slice(offset, end).arrayBuffer();
                await channel.send({
                    type: "chunk",
                    offset,
                    data: encodeVideoChunk(chunk)
                });
            }

            const result = await channel.send({ type: "finish" });
            console.log("✅ VIDEO COPIED SUCCESSFULLY", result);
            return result;
        } finally {
            channel.close();
        }
    }

    async function copyVideoWithStash(video) {
        if (copyJobActive) return { success: false, error: "A video copy is already in progress." };
        if (!video) return { success: false, error: "No video was found in this tab." };

        copyJobActive = true;
        selectVideo(video);
        showCopyButton(video);
        let snapshot = null;
        const setButton = (label, title = "") => {
            if (!copyButton) return;
            copyButton.textContent = label;
            copyButton.title = title;
            copyButton.style.visibility = "visible";
        };
        if (copyButton) {
            copyButton.disabled = true;
            setButton("⏳ Copying video…");
        }

        try {
            snapshot = await getClipboardSnapshotBeforeCapture(video);
            const clipboardChangeCount = snapshot.clipboardChangeCount;
            const pendingItemId = snapshot.itemId;
            await updateVideoCopyStatus(pendingItemId, "downloading");
            let uploadResult = await tryDirectVideo(video, snapshot);

            if (!uploadResult) {
                await updateVideoCopyStatus(pendingItemId, "capturing");
                setButton("⏺ Capturing video…");
                if (copyButton) copyButton.style.visibility = "hidden";
                const blob = await captureVideo(video);
                await updateVideoCopyStatus(pendingItemId, "saving");
                setButton("⏳ Saving to Stash…");
                uploadResult = await uploadVideo(blob, video, clipboardChangeCount, pendingItemId);
            }

            setButton(uploadResult.clipboard_published ? "✅ Copied" : "✅ Saved only");
            return {
                success: true,
                clipboard_published: uploadResult.clipboard_published === true,
                message: uploadResult.message || "Video copied to Stash."
            };
        } catch (error) {
            await cancelPendingVideo(snapshot?.itemId);
            setButton(error.code === "video_copy_disabled" ? "🔒 Allow in Stash" : "❌ Failed", error.message || "Video copying failed.");
            return {
                success: false,
                error: error.message || "Video copying failed.",
                code: error.code || ""
            };
        } finally {
            copyJobActive = false;
            if (copyButton) copyButton.disabled = false;
            setTimeout(() => {
                if (copyButton) {
                    copyButton.textContent = "⚡ Copy with Stash";
                    copyButton.title = "";
                }
            }, 2500);
        }
    }

    // =========================================================
    // COPY BUTTON
    // =========================================================

    function showCopyButton(video) {
        if (isStashLibraryPage) {
            return;
        }
        if (!copyButton) {
            copyButton =
                document.createElement("button");

            copyButton.textContent =
                "⚡ Copy with Stash";

            copyButton.style.position =
                "fixed";

            copyButton.style.zIndex =
                "2147483647";

            copyButton.style.padding =
                "10px 14px";

            copyButton.style.border =
                "none";

            copyButton.style.borderRadius =
                "8px";

            copyButton.style.background =
                "#000";

            copyButton.style.color =
                "#fff";

            copyButton.style.fontSize =
                "13px";

            copyButton.style.cursor =
                "pointer";

            copyButton.style.boxShadow =
                "0 4px 20px rgba(0,0,0,.4)";

            document.body.appendChild(
                copyButton
            );

            copyButton.addEventListener(
                "click",
                async event => {
                    event.preventDefault();
                    event.stopPropagation();
                    const result = await copyVideoWithStash(selectedVideo);
                    if (!result.success) console.error("❌ Stash video error:", result.error);
                }
            );
        }

        const rect =
            video.getBoundingClientRect();

        copyButton.style.left =
            `${Math.max(10, rect.left + 20)}px`;

        copyButton.style.top =
            `${Math.max(10, rect.top + 20)}px`;

        copyButton.style.display =
            "block";
    }

    // =========================================================
    // BACKGROUND / CONTEXT MENU
    // =========================================================

    chrome.runtime.onMessage.addListener(
        async (message, sender, sendResponse) => {

            if (message?.type === "VIDEO_COPY_STAGE") {
                if (copyButton && copyButton.disabled) {
                    copyButton.textContent = message.stage === "saving"
                        ? "⏳ Saving to Stash…"
                        : "⏳ Downloading video…";
                }
                return false;
            }

            if (message?.type === "STASH_PING") {
                sendResponse({ ready: true });
                return false;
            }

            if (message?.type === "COPY_VIDEO_NOW") {
                const video = findVideoForCopy();
                if (!video) {
                    return {
                        success: false,
                        error: "No video found. Play one first."
                    };
                }
                return copyVideoWithStash(video);
            }

            if (message?.type === "GET_AUDIO_CONTEXT") {
                const audioElements = [
                    ...document.querySelectorAll("audio")
                ];

                const getAudioUrl = element =>
                    element.currentSrc ||
                    element.src ||
                    element.querySelector("source[src]")?.src ||
                    "";

                // Prefer the audio that is actually playing.
                const playing = audioElements.filter(element =>
                    !element.paused &&
                    !element.ended &&
                    getAudioUrl(element)
                );

                let url = "";

                if (playing.length === 1) {
                    url = getAudioUrl(playing[0]);
                } else if (playing.length > 1) {
                    console.warn(
                        "Stash: Multiple audio elements are playing; " +
                        "select a specific audio link instead."
                    );
                } else if (audioElements.length === 1) {
                    url = getAudioUrl(audioElements[0]);
                }

                // Only use a direct audio link when there is exactly one.
                if (!url) {
                    const audioExtensions =
                        /\.(mp3|m4a|aac|ogg|oga|opus|wav|flac|aiff?)(?:[?#]|$)/i;

                    const links = [
                        ...document.querySelectorAll("a[href]")
                    ].filter(link => audioExtensions.test(link.href));

                    if (links.length === 1) {
                        url = links[0].href;
                    }
                }

                if (!url) {
                    console.warn(
                        "Stash: Audio source is ambiguous. " +
                        "Right-click the specific audio link instead."
                    );
                }

                sendResponse({
                    url,
                    page_url: window.location.href,
                    title: document.title
                });

                return true;
            }

            if (
                message?.type ===
                "GET_CONTEXT"
            ) {

                if (selectedVideo) {
                    sendResponse({
                        type: "video",

                        url:
                            selectedVideo.currentSrc ||
                            selectedVideo.src ||
                            "",

                        page_url:
                            window.location.href,

                        title:
                            document.title,

                        mime_type:
                            selectedVideo.currentSrc
                                ? "video/webm"
                                : ""
                    });

                } else {

                    sendResponse({
                        type: "text"
                    });
                }

                return true;
            }

            if (
                message?.type ===
                "CAPTURE_VIDEO"
            ) {

                try {

                    if (!selectedVideo) {
                        throw new Error(
                            "No video selected."
                        );
                    }

                    const video =
                        selectedVideo;

                    console.log(
                        "🔒 BACKGROUND VIDEO LOCKED"
                    );

                    const blob =
                        await captureVideo(
                            video
                        );

                    const arrayBuffer =
                        await blob.arrayBuffer();

                    console.log(
                        "🎥 Background capture ready:",
                        arrayBuffer.byteLength,
                        "bytes"
                    );

                    sendResponse({
                        success: true,

                        bytes:
                            arrayBuffer,

                        size:
                            arrayBuffer.byteLength,

                        mimeType:
                            blob.type,

                        url:
                            video.currentSrc ||
                            video.src ||
                            "",

                        page_url:
                            window.location.href,

                        title:
                            document.title
                    });

                } catch (error) {

                    console.error(
                        "❌ Background capture failed:",
                        error
                    );

                    sendResponse({
                        success: false,
                        error: error.message
                    });
                }

                return true;
            }
        }
    );

})();
