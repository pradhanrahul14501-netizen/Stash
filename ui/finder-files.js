"use strict";

/* Read-only access to one folder chosen by the user. File handles stay in this browser and file bytes are never sent to the server. */
(() => {
    const databaseName = "copy-maker-folder-access";
    const storeName = "permissions";
    const handleKey = "selected-root";

    const connectButton = document.getElementById("connectFinderFolderButton");
    const changeButton = document.getElementById("changeFinderFolderButton");
    const disconnectButton = document.getElementById("disconnectFinderFolderButton");
    const accessStatus = document.getElementById("finderAccessStatus");
    const navButton = document.getElementById("finderNavigation");
    const fallbackPicker = document.getElementById("finderFallbackPicker");
    const refreshButton = document.getElementById("finderRefreshButton");
    const searchInput = document.getElementById("finderSearchInput");
    const fileList = document.getElementById("finderFileList");
    const status = document.getElementById("finderStatus");
    const currentPath = document.getElementById("finderCurrentPath");
    const breadcrumbs = document.getElementById("finderBreadcrumbs");
    const previewDialog = document.getElementById("finderPreviewDialog");
    const previewTitle = document.getElementById("finderPreviewTitle");
    const previewContent = document.getElementById("finderPreviewContent");
    const closePreviewButton = document.getElementById("closeFinderPreview");
    const avaFolderPath = document.getElementById("avaConnectedFolderPath");
    const connectAvaFolderButton = document.getElementById("connectAvaFolderButton");
    const disconnectAvaFolderButton = document.getElementById("disconnectAvaFolderButton");
    const avaFolderStatus = document.getElementById("avaConnectedFolderStatus");

    let rootHandle = null;
    let directoryStack = [];
    let currentEntries = [];
    let sessionFiles = null;
    let sessionFolderName = "";
    let readAccess = false;
    let previewUrl = "";

    function setStatus(element, message, kind = "") {
        if (!element) return;
        element.textContent = message;
        if (kind) element.dataset.kind = kind;
        else delete element.dataset.kind;
    }

    async function updateAvaFolderAccess({ folder, disconnect = false } = {}) {
        if (!avaFolderStatus) return;
        if (connectAvaFolderButton) connectAvaFolderButton.disabled = true;
        if (disconnectAvaFolderButton) disconnectAvaFolderButton.disabled = true;
        try {
            const response = await fetch("/api/ava/folder-access", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(disconnect ? { disconnect: true } : { folder }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.message || "Ava could not connect this folder.");
            setStatus(avaFolderStatus, result.message || "Ava folder access updated.", "success");
            if (disconnect) {
                if (avaFolderPath) avaFolderPath.value = "";
                if (disconnectAvaFolderButton) disconnectAvaFolderButton.hidden = true;
            } else if (disconnectAvaFolderButton) {
                disconnectAvaFolderButton.hidden = false;
            }
        } catch (error) {
            setStatus(avaFolderStatus, error?.message || "Stash could not update Ava's folder access.", "error");
        } finally {
            if (connectAvaFolderButton) connectAvaFolderButton.disabled = false;
            if (disconnectAvaFolderButton) disconnectAvaFolderButton.disabled = false;
        }
    }

    async function restoreAvaFolderAccess() {
        if (!avaFolderStatus) return;
        try {
            const response = await fetch("/api/ava/folder-access", { headers: { "Accept": "application/json" } });
            const result = await response.json();
            if (!response.ok) throw new Error(result.message || "Folder access status could not be loaded.");
            if (result.connected) {
                if (disconnectAvaFolderButton) disconnectAvaFolderButton.hidden = false;
                setStatus(avaFolderStatus, `Ava is connected to “${result.folder_name}” and its subfolders.`, "success");
            }
        } catch (error) {
            setStatus(avaFolderStatus, error?.message || "Ava folder access status could not be loaded.", "error");
        }
    }

    connectAvaFolderButton?.addEventListener("click", () => {
        const folder = avaFolderPath?.value.trim();
        if (!folder) {
            setStatus(avaFolderStatus, "Enter the full path to one folder first.", "error");
            avaFolderPath?.focus();
            return;
        }
        updateAvaFolderAccess({ folder });
    });
    disconnectAvaFolderButton?.addEventListener("click", () => updateAvaFolderAccess({ disconnect: true }));
    restoreAvaFolderAccess();

    function openDatabase() {
        return new Promise((resolve, reject) => {
            if (!window.indexedDB) {
                reject(new Error("This browser cannot remember a folder connection."));
                return;
            }
            const request = indexedDB.open(databaseName, 1);
            request.onupgradeneeded = () => {
                const database = request.result;
                if (!database.objectStoreNames.contains(storeName)) {
                    database.createObjectStore(storeName);
                }
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error || new Error("Folder access could not be saved."));
        });
    }

    async function loadHandle() {
        const database = await openDatabase();
        try {
            return await new Promise((resolve, reject) => {
                const transaction = database.transaction(storeName, "readonly");
                const request = transaction.objectStore(storeName).get(handleKey);
                request.onsuccess = () => resolve(request.result || null);
                request.onerror = () => reject(request.error || new Error("Saved folder access could not be read."));
            });
        } finally {
            database.close();
        }
    }

    async function saveHandle(handle) {
        const database = await openDatabase();
        try {
            await new Promise((resolve, reject) => {
                const transaction = database.transaction(storeName, "readwrite");
                transaction.objectStore(storeName).put(handle, handleKey);
                transaction.oncomplete = resolve;
                transaction.onerror = () => reject(transaction.error || new Error("Folder access could not be saved."));
                transaction.onabort = () => reject(transaction.error || new Error("Folder access could not be saved."));
            });
        } finally {
            database.close();
        }
    }

    async function forgetHandle() {
        const database = await openDatabase();
        try {
            await new Promise((resolve, reject) => {
                const transaction = database.transaction(storeName, "readwrite");
                transaction.objectStore(storeName).delete(handleKey);
                transaction.oncomplete = resolve;
                transaction.onerror = () => reject(transaction.error || new Error("The folder connection could not be removed."));
                transaction.onabort = () => reject(transaction.error || new Error("The folder connection could not be removed."));
            });
        } finally {
            database.close();
        }
    }

    function updateConnectionUI(granted, message = "") {
        readAccess = granted === true;
        if (navButton) navButton.hidden = !readAccess;
        if (connectButton) {
            connectButton.hidden = readAccess;
            connectButton.textContent = rootHandle ? "Allow access" : "Allow folder access";
            connectButton.disabled = !window.showDirectoryPicker && !(fallbackPicker && "webkitdirectory" in fallbackPicker) && !rootHandle;
        }
        if (changeButton) changeButton.hidden = !rootHandle && !sessionFiles;
        if (disconnectButton) disconnectButton.hidden = !rootHandle && !sessionFiles;
        if (!readAccess) {
            directoryStack = [];
            currentEntries = [];
            sessionFiles = null;
            sessionFolderName = "";
            fileList?.replaceChildren();
            breadcrumbs?.replaceChildren();
            if (refreshButton) refreshButton.disabled = true;
            if (currentPath) currentPath.textContent = "Connect a folder in Settings to browse its files.";
            if (status) status.textContent = "Your selected folder’s files will appear here.";
        } else if (refreshButton) {
            refreshButton.disabled = false;
        }
        if (message) setStatus(accessStatus, message, granted ? "success" : "");
        document.dispatchEvent(new CustomEvent("stash:finder-access-changed", {
            detail: { granted: readAccess },
        }));
    }

    async function permissionState(handle) {
        if (!handle) return "denied";
        if (typeof handle.queryPermission !== "function") return "denied";
        try {
            return await handle.queryPermission({ mode: "read" });
        } catch {
            return "denied";
        }
    }

    async function requestPermission(handle) {
        if (typeof handle.requestPermission === "function") {
            return (await handle.requestPermission({ mode: "read" })) === "granted";
        }
        return (await permissionState(handle)) === "granted";
    }

    function displayFolderName() {
        return directoryStack.map(handle => handle.name).join(" / ") || sessionFolderName;
    }

    function makeBreadcrumb(label, index, enabled) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "finder-breadcrumb";
        button.textContent = label;
        button.disabled = !enabled;
        button.addEventListener("click", () => {
            if (!enabled) return;
            directoryStack = directoryStack.slice(0, index + 1);
            openCurrentDirectory();
        });
        return button;
    }

    function renderBreadcrumbs() {
        if (!breadcrumbs || (!rootHandle && !sessionFolderName)) return;
        breadcrumbs.replaceChildren();
        const rootName = (directoryStack[0] || rootHandle)?.name || sessionFolderName;
        breadcrumbs.append(makeBreadcrumb(rootName, 0, Boolean(rootHandle && directoryStack.length > 1)));
        for (let index = 1; index < directoryStack.length; index += 1) {
            const separator = document.createElement("span");
            separator.className = "finder-breadcrumb-separator";
            separator.setAttribute("aria-hidden", "true");
            separator.textContent = "/";
            breadcrumbs.append(separator, makeBreadcrumb(directoryStack[index].name, index, index < directoryStack.length - 1));
        }
    }

    function formatBytes(bytes) {
        const value = Number(bytes) || 0;
        if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
        if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`;
        if (value >= 1024) return `${(value / 1024).toFixed(0)} KB`;
        return `${value} B`;
    }

    function formatModified(timestamp) {
        if (!timestamp) return "";
        const date = new Date(timestamp);
        return Number.isNaN(date.getTime()) ? "" : date.toLocaleString();
    }

    function createFilePreview(file) {
        if (!previewContent || !previewDialog) return;
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewContent.replaceChildren();
        previewTitle.textContent = file.name;
        previewUrl = URL.createObjectURL(file);
        const extension = file.name.split(".").pop()?.toLocaleLowerCase() || "";
        const extensionTypes = {
            mp4: "video/mp4", m4v: "video/mp4", mov: "video/quicktime", webm: "video/webm", ogv: "video/ogg",
            mp3: "audio/mpeg", m4a: "audio/mp4", wav: "audio/wav", ogg: "audio/ogg", flac: "audio/flac",
            png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif", webp: "image/webp", svg: "image/svg+xml",
            pdf: "application/pdf", txt: "text/plain", md: "text/markdown", csv: "text/csv", json: "application/json",
        };
        const type = file.type && file.type !== "application/octet-stream"
            ? file.type
            : extensionTypes[extension] || file.type || "";
        let preview;
        if (type.startsWith("video/")) {
            preview = document.createElement("video");
            preview.controls = true;
            preview.playsInline = true;
        } else if (type.startsWith("audio/")) {
            preview = document.createElement("audio");
            preview.controls = true;
        } else if (type.startsWith("image/")) {
            preview = document.createElement("img");
            preview.alt = file.name;
        } else if (type === "application/pdf" || type.startsWith("text/")) {
            preview = document.createElement("iframe");
            preview.title = `Preview of ${file.name}`;
            preview.setAttribute("sandbox", "allow-downloads");
        } else {
            const message = document.createElement("p");
            message.className = "finder-preview-message";
            message.textContent = "This file type can’t be previewed here. Download it to open it in another app.";
            const download = document.createElement("a");
            download.className = "settings-primary-button settings-link-button";
            download.href = previewUrl;
            download.download = file.name;
            download.textContent = "Download file";
            previewContent.append(message, download);
            previewDialog.showModal();
            return;
        }
        preview.src = previewUrl;
        preview.className = "finder-preview-media";
        previewContent.append(preview);
        previewDialog.showModal();
    }

    function closePreview() {
        if (previewDialog?.open) previewDialog.close();
        previewContent?.replaceChildren();
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewUrl = "";
    }

    async function openFile(entry) {
        try {
            if (rootHandle && (await permissionState(rootHandle)) !== "granted") {
                updateConnectionUI(false, "Folder access is off. Allow access in Settings to show files again.");
                return;
            }
            const file = entry.file || await entry.handle.getFile();
            createFilePreview(file);
        } catch (error) {
            if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
                updateConnectionUI(false, "Folder access was removed. Allow access again in Settings to show files.");
                return;
            }
            setStatus(status, error?.name === "NotFoundError"
                ? "This file is no longer in the selected folder. Refresh the list."
                : "Stash could not open this file.", "error");
        }
    }

    async function downloadFile(entry) {
        try {
            if (rootHandle && (await permissionState(rootHandle)) !== "granted") {
                updateConnectionUI(false, "Folder access is off. Allow access in Settings to show files again.");
                return;
            }
            const file = entry.file || await entry.handle.getFile();
            const url = URL.createObjectURL(file);
            const anchor = document.createElement("a");
            anchor.href = url;
            anchor.download = file.name;
            anchor.hidden = true;
            document.body.append(anchor);
            anchor.click();
            anchor.remove();
            window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
        } catch (error) {
            const message = error?.name === "NotAllowedError"
                ? "Folder access was removed. Allow access again in Settings to show files."
                : "Stash could not download this file.";
            setStatus(status, message, "error");
            if (error?.name === "NotAllowedError") updateConnectionUI(false, message);
        }
    }

    function renderEntries() {
        if (!fileList) return;
        const query = (searchInput?.value || "").trim().toLocaleLowerCase();
        const visibleEntries = currentEntries.filter(entry => entry.name.toLocaleLowerCase().includes(query));
        fileList.replaceChildren();
        if (!visibleEntries.length) {
            const empty = document.createElement("p");
            empty.className = "finder-empty-state";
            empty.textContent = query ? "No names match your search." : "This folder is empty.";
            fileList.append(empty);
            return;
        }

        const fragment = document.createDocumentFragment();
        for (const entry of visibleEntries) {
            const row = document.createElement("article");
            row.className = "finder-file-row";
            const icon = document.createElement("span");
            icon.className = "finder-file-icon";
            icon.setAttribute("aria-hidden", "true");
            icon.textContent = entry.kind === "directory" ? "▰" : "▤";

            const details = document.createElement("div");
            details.className = "finder-file-details";
            const name = document.createElement("strong");
            name.className = "finder-file-name";
            name.textContent = entry.name;
            const metadata = document.createElement("span");
            metadata.className = "finder-file-meta";
            metadata.textContent = entry.kind === "directory"
                ? "Folder"
                : [formatBytes(entry.size), formatModified(entry.lastModified)].filter(Boolean).join(" · ");
            details.append(name, metadata);

            const actions = document.createElement("div");
            actions.className = "finder-file-actions";
            const open = document.createElement("button");
            open.type = "button";
            open.className = "settings-secondary-button";
            open.textContent = entry.kind === "directory" ? "Open folder" : "Open";
            open.addEventListener("click", () => {
                if (entry.kind === "directory") {
                    directoryStack.push(entry.handle);
                    openCurrentDirectory();
                } else {
                    openFile(entry);
                }
            });
            actions.append(open);
            if (entry.kind === "file") {
                const download = document.createElement("button");
                download.type = "button";
                download.className = "settings-secondary-button";
                download.textContent = "Download";
                download.addEventListener("click", () => downloadFile(entry));
                actions.append(download);
            }
            row.append(icon, details, actions);
            fragment.append(row);
        }
        fileList.append(fragment);
    }

    async function openCurrentDirectory() {
        if (!readAccess) return;
        if (!rootHandle && sessionFiles) {
            renderBreadcrumbs();
            if (currentPath) currentPath.textContent = `${sessionFolderName} · available until this page closes`;
            setStatus(status, `${sessionFiles.length} ${sessionFiles.length === 1 ? "file" : "files"} selected. Files stay on this device.`);
            renderEntries();
            return;
        }
        if (!rootHandle) return;
        const handle = directoryStack[directoryStack.length - 1] || rootHandle;
        if (refreshButton) refreshButton.disabled = true;
        if (fileList) fileList.replaceChildren();
        setStatus(status, "Loading folder…");
        try {
            if ((await permissionState(rootHandle)) !== "granted") {
                updateConnectionUI(false, "Folder access is off. Allow access in Settings to show files again.");
                return;
            }
            const entries = [];
            for await (const [name, childHandle] of handle.entries()) {
                if (childHandle.kind === "directory") {
                    entries.push({ name, handle: childHandle, kind: "directory", size: 0, lastModified: 0 });
                } else {
                    const file = await childHandle.getFile();
                    entries.push({ name, handle: childHandle, kind: "file", size: file.size, lastModified: file.lastModified });
                }
            }
            currentEntries = entries.sort((left, right) => {
                if (left.kind !== right.kind) return left.kind === "directory" ? -1 : 1;
                return left.name.localeCompare(right.name, undefined, { numeric: true, sensitivity: "base" });
            });
            renderBreadcrumbs();
            if (currentPath) currentPath.textContent = displayFolderName();
            setStatus(status, `${currentEntries.length} ${currentEntries.length === 1 ? "item" : "items"} in this folder. Files stay on this device.`);
            renderEntries();
        } catch (error) {
            currentEntries = [];
            fileList?.replaceChildren();
            if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
                updateConnectionUI(false, "Folder access was removed. Allow access again in Settings to show files.");
            } else {
                setStatus(status, error?.name === "NotFoundError"
                    ? "The selected folder can’t be found. Choose it again in Settings."
                    : "Stash could not read this folder. Try refreshing or choose it again.", "error");
            }
        } finally {
            if (refreshButton) refreshButton.disabled = !readAccess;
        }
    }

    async function chooseFolder() {
        if (!window.showDirectoryPicker) {
            if (fallbackPicker && "webkitdirectory" in fallbackPicker) {
                fallbackPicker.click();
                return;
            }
            setStatus(accessStatus, "Folder access is supported in Chrome or Edge. This browser cannot connect a folder.", "error");
            return;
        }
        if (!window.isSecureContext) {
            setStatus(accessStatus, "Open Stash on this device through its secure local address to connect a folder.", "error");
            return;
        }
        connectButton.disabled = true;
        changeButton && (changeButton.disabled = true);
        setStatus(accessStatus, "Choose the folder Stash may browse…");
        try {
            const handle = await window.showDirectoryPicker({ mode: "read" });
            const granted = (await permissionState(handle)) === "granted";
            if (!granted) {
                await saveHandle(handle);
                rootHandle = handle;
                directoryStack = [];
                updateConnectionUI(false, "Folder selected. Click Allow access to finish granting permission; files remain hidden until then.");
                return;
            }
            await saveHandle(handle);
            rootHandle = handle;
            sessionFiles = null;
            sessionFolderName = "";
            directoryStack = [handle];
            updateConnectionUI(true, `Connected to “${handle.name}”. Only this folder and its subfolders are visible.`);
            await openCurrentDirectory();
        } catch (error) {
            if (error?.name === "AbortError") {
                setStatus(accessStatus, rootHandle || sessionFiles
                    ? "Folder selection was cancelled. Your previous folder selection is unchanged."
                    : "Folder selection was cancelled. No files are shown.");
            } else {
                setStatus(accessStatus, error?.message || "Stash could not connect that folder.", "error");
            }
        } finally {
            if (connectButton) connectButton.disabled = false;
            if (changeButton) changeButton.disabled = false;
        }
    }

    async function allowSavedFolder() {
        if (!rootHandle) return chooseFolder();
        connectButton.disabled = true;
        setStatus(accessStatus, "Requesting access to the selected folder…");
        try {
            const granted = await requestPermission(rootHandle);
            if (!granted) {
                updateConnectionUI(false, "Access wasn’t allowed. No files are shown.");
                return;
            }
            directoryStack = [rootHandle];
            updateConnectionUI(true, `Connected to “${rootHandle.name}”. Only this folder and its subfolders are visible.`);
        } catch (error) {
            setStatus(accessStatus, error?.message || "Stash could not request folder access.", "error");
        } finally {
            if (connectButton) connectButton.disabled = false;
        }
    }

    async function disconnectFolder() {
        disconnectButton.disabled = true;
        try {
            await forgetHandle();
            rootHandle = null;
            directoryStack = [];
            currentEntries = [];
            sessionFiles = null;
            sessionFolderName = "";
            updateConnectionUI(false, "Folder disconnected. Its files are hidden from Stash.");
        } catch (error) {
            setStatus(accessStatus, error?.message || "The folder could not be disconnected.", "error");
        } finally {
            if (disconnectButton) disconnectButton.disabled = false;
        }
    }

    async function restoreFolder() {
        if (!window.showDirectoryPicker) {
            const fallbackAvailable = Boolean(fallbackPicker && "webkitdirectory" in fallbackPicker);
            if (connectButton) connectButton.disabled = !fallbackAvailable;
            setStatus(accessStatus, fallbackAvailable
                ? "Choose a folder to browse its files for this session. The browser will ask again after a reload."
                : "Folder access is supported in Chrome or Edge on this device.");
            return;
        }
        try {
            rootHandle = await loadHandle();
            if (!rootHandle) {
                updateConnectionUI(false, "No folder is connected. Files stay hidden until you choose one.");
                return;
            }
            const granted = (await permissionState(rootHandle)) === "granted";
            if (granted) {
                directoryStack = [rootHandle];
                updateConnectionUI(true, `Connected to “${rootHandle.name}”. Only this folder and its subfolders are visible.`);
            } else {
                updateConnectionUI(false, `“${rootHandle.name}” is remembered, but access is off. Allow access to show its files.`);
            }
        } catch (error) {
            rootHandle = null;
            updateConnectionUI(false, error?.message || "Saved folder access could not be restored.");
        }
    }

    connectButton?.addEventListener("click", allowSavedFolder);
    changeButton?.addEventListener("click", chooseFolder);
    disconnectButton?.addEventListener("click", disconnectFolder);
    fallbackPicker?.addEventListener("change", () => {
        const files = Array.from(fallbackPicker.files || []);
        fallbackPicker.value = "";
        if (!files.length) {
            setStatus(accessStatus, "No files were selected. No files are shown.");
            return;
        }
        const firstPath = files[0].webkitRelativePath || files[0].name;
        sessionFolderName = firstPath.split("/")[0] || "Selected folder";
        sessionFiles = files;
        rootHandle = null;
        directoryStack = [];
        currentEntries = files.map(file => ({
            name: file.webkitRelativePath || file.name,
            handle: null,
            file,
            kind: "file",
            size: file.size,
            lastModified: file.lastModified,
        })).sort((left, right) => left.name.localeCompare(right.name, undefined, { numeric: true, sensitivity: "base" }));
        updateConnectionUI(true, `Connected to “${sessionFolderName}” for this session. Nothing is uploaded.`);
        if (currentPath) currentPath.textContent = `${sessionFolderName} · available until this page closes`;
        setStatus(status, `${sessionFiles.length} ${sessionFiles.length === 1 ? "file" : "files"} selected. Files stay on this device.`);
        renderBreadcrumbs();
        renderEntries();
    });
    refreshButton?.addEventListener("click", openCurrentDirectory);
    searchInput?.addEventListener("input", renderEntries);
    closePreviewButton?.addEventListener("click", closePreview);
    previewDialog?.addEventListener("close", closePreview);
    window.StashFinderFiles = {
        hasReadAccess: () => readAccess,
        openCurrentDirectory,
    };

    restoreFolder();
})();
