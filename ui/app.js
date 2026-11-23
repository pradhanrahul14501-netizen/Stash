"use strict";


/* =========================================================
   STASH UI V2
   Stash library, Bin, and copy interaction layer.
========================================================= */


/* =========================================================
   DOM
========================================================= */

const app =
    document.getElementById("app");

const sidebar =
    document.getElementById("sidebar");

const libraryWorkspace =
    document.getElementById("libraryWorkspace");

const chatWorkspace =
    document.getElementById("chatWorkspace");

const finderWorkspace = document.getElementById("finderWorkspace");
const finderNavigation = document.getElementById("finderNavigation");

const sidebarOverlay =
    document.getElementById("sidebarOverlay");

const grid =
    document.getElementById("itemsContainer");

const searchInput =
    document.getElementById("searchInput");

const clearSearch =
    document.getElementById("clearSearch");

const resultSummary =
    document.getElementById("resultSummary");

const emptyState =
    document.getElementById("emptyState");

const loadMoreContainer =
    document.getElementById("loadMoreContainer");

const loadMoreButton =
    document.getElementById("loadMoreButton");

const dateNavigation =
    document.getElementById("dateNavigation");

const folderNavigation = document.getElementById("folderNavigation");
const folderSection = document.getElementById("folderSection");
const dateJumpForm = document.getElementById("dateJumpForm");
const dateJumpInput = document.getElementById("dateJumpInput");
const timeJumpInput = document.getElementById("timeJumpInput");
const dateJumpStatus = document.getElementById("dateJumpStatus");
const filterSummaryText = document.getElementById("filterSummaryText");
const filterDisclosure = document.getElementById("filterDisclosure");
const moveFolderSelect = document.getElementById("moveFolderSelect");

const copyViewer =
    document.getElementById("copyViewer");

const viewerTitle =
    document.getElementById("viewerTitle");

const viewerContent =
    document.getElementById("viewerContent");

const binNavigation = document.getElementById("binNavigation");
const binPanel = document.getElementById("binPanel");
const libraryBulkActions = document.getElementById("libraryBulkActions");
const binEmptyAt = document.getElementById("binEmptyAt");
const sendSelectedCopiesButton = document.getElementById("sendSelectedCopiesButton");
const deviceTransferDialog = document.getElementById("deviceTransferDialog");
const deviceTransferForm = document.getElementById("deviceTransferForm");
const deviceTransferReceiverUrl = document.getElementById("deviceTransferReceiverUrl");
const deviceTransferPairCode = document.getElementById("deviceTransferPairCode");
const deviceTransferStartButton = document.getElementById("startDeviceTransferButton");
const deviceTransferProgress = document.getElementById("deviceTransferProgress");
const deviceTransferProgressBar = document.getElementById("deviceTransferProgressBar");
const deviceTransferProgressText = document.getElementById("deviceTransferProgressText");
const deviceTransferDialogStatus = document.getElementById("deviceTransferDialogStatus");
const deviceTransferCloseButtons = [
    document.getElementById("closeDeviceTransferDialog"),
    document.getElementById("closeDeviceTransferDialogAction"),
];


/* =========================================================
   STATE
========================================================= */

let allItems = [];
let binItems = [];
let folders = [];
let foldersLoaded = false;
let binSettings = { empty_at: null, reminder_sent_for: null };
let activeView = "library";
let finderWorkspaceOpen = false;
let selectedItemIds = new Set();
let deviceTransferInProgress = false;
const ALL_FOLDERS = Symbol("all-folders");
let activeFolder = ALL_FOLDERS;

let activeType = "all";

let activeWorkspaceMode = "all";

let activeDate = "all";
let activeTime = "";

let sortNewestFirst = true;

let visibleLimit = 60;

const PAGE_SIZE = 60;


function closeMobileSidebar() {
    sidebar?.classList.remove("mobile-open");
    if (sidebarOverlay) sidebarOverlay.hidden = true;
    document.querySelectorAll(".mobile-menu-toggle").forEach(button => {
        button.setAttribute("aria-expanded", "false");
        button.setAttribute("aria-label", "Open navigation");
    });
}


function showLibraryWorkspace() {
    const returningFromBin = activeView === "bin";
    if (returningFromBin) selectedItemIds.clear();
    activeView = "library";
    finderWorkspaceOpen = false;
    if (libraryWorkspace) libraryWorkspace.hidden = false;
    if (chatWorkspace) chatWorkspace.hidden = true;
    if (finderWorkspace) finderWorkspace.hidden = true;
    closeMobileSidebar();
    updateViewChrome();
    if (returningFromBin) {
        document.querySelector('.nav-item[data-type="all"]')?.classList.add("active");
        document.querySelector('.filter-button[data-filter="all"]:not([data-mode])')?.classList.add("active");
    }
}


function showBinWorkspace() {
    activeView = "bin";
    finderWorkspaceOpen = false;
    activeType = "all";
    activeWorkspaceMode = "all";
    activeDate = "all";
    activeTime = "";
    activeFolder = ALL_FOLDERS;
    selectedItemIds.clear();
    updateFilterSummary();
    if (searchInput) searchInput.value = "";
    updateSearchUI();
    if (libraryWorkspace) libraryWorkspace.hidden = false;
    if (chatWorkspace) chatWorkspace.hidden = true;
    if (finderWorkspace) finderWorkspace.hidden = true;
    document.querySelectorAll(".filter-button").forEach(button => button.classList.remove("active"));
    document.querySelectorAll(".nav-item[data-type]").forEach(button => button.classList.remove("active"));
    closeMobileSidebar();
    updateViewChrome();
    buildFolderNavigation();
    buildDateNavigation();
    updateBinControls();
    renderItems();
}


function getActiveItems() {
    return activeView === "bin" ? binItems : allItems;
}


function getActiveItemDate(item) {
    if (activeView === "bin" && item?.trashed_at) {
        const deletedAt = new Date(item.trashed_at);
        if (!Number.isNaN(deletedAt.getTime())) return deletedAt;
    }
    return getItemDate(item);
}


function updateViewChrome() {
    const title = document.querySelector(".page-title h1");
    const subtitle = document.getElementById("librarySubtitle");
    const folderTitle = activeFolder === ALL_FOLDERS
        ? "All copies"
        : activeFolder === null
            ? "Unfiled"
            : activeFolder;
    if (title) title.textContent = activeView === "bin" ? "Bin" : folderTitle;
    if (subtitle) {
        subtitle.textContent = activeView === "bin"
            ? "Copies you moved here. Restore them or empty the Bin on a schedule."
            : activeFolder === ALL_FOLDERS
                ? "New copies appear here automatically."
                : activeFolder === null
                    ? "Copies that are not in a folder."
                    : `Copies saved in ${activeFolder}.`;
    }
    if (libraryBulkActions) libraryBulkActions.hidden = activeView === "bin";
    if (binPanel) binPanel.hidden = activeView !== "bin";
    if (folderSection) folderSection.hidden = activeView === "bin";
    binNavigation?.classList.toggle("active", activeView === "bin");
    finderNavigation?.classList.toggle("active", finderWorkspaceOpen);
    updateSelectionControls();
}


function updateSelectionControls() {
    const currentItems = getFilteredItems();
    const selectedCount = selectedItemIds.size;
    const summary = document.getElementById("selectionSummary");
    const selectAllButton = document.getElementById("selectAllButton");
    const selectAllBinButton = document.getElementById("selectAllBinButton");
    const binSummary = document.getElementById("binSelectionSummary");
    const moveButton = document.getElementById("moveToBinButton");
    const moveToFolderButton = document.getElementById("moveToFolderButton");
    const restoreButton = document.getElementById("restoreSelectedButton");
    const sendButton = document.getElementById("sendSelectedCopiesButton");
    const allVisibleSelected = currentItems.length > 0 && currentItems.every(item => selectedItemIds.has(Number(item.id)));
    if (summary) summary.textContent = selectedCount
        ? `${selectedCount} ${selectedCount === 1 ? "copy" : "copies"} selected`
        : "Select copies to organize or send them together.";
    if (selectAllButton) selectAllButton.textContent = allVisibleSelected ? "Clear selection" : "Select all";
    if (selectAllBinButton) selectAllBinButton.textContent = allVisibleSelected ? "Clear selection" : "Select all";
    if (binSummary) binSummary.textContent = selectedCount
        ? `${selectedCount} ${selectedCount === 1 ? "copy" : "copies"} selected`
        : "Select copies to restore them together.";
    if (moveButton) moveButton.disabled = selectedCount === 0;
    if (moveFolderSelect) moveFolderSelect.disabled = selectedCount === 0;
    if (moveToFolderButton) moveToFolderButton.disabled = selectedCount === 0 || !moveFolderSelect?.value;
    if (restoreButton) restoreButton.disabled = selectedCount === 0;
    if (sendButton) sendButton.disabled = selectedCount === 0 || activeView === "bin";
    const emptyButton = document.getElementById("emptyBinButton");
    if (emptyButton) emptyButton.disabled = binItems.length === 0;
}


function updateBinControls() {
    const input = binEmptyAt;
    const status = document.getElementById("binScheduleStatus");
    const cancelButton = document.getElementById("cancelBinScheduleButton");
    if (input) {
        if (document.activeElement !== input) {
            input.value = binSettings.empty_at
                ? new Date(new Date(binSettings.empty_at).getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16)
                : "";
        }
        const min = new Date(Date.now() + 60000);
        input.min = new Date(min.getTime() - min.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    }
    if (status) status.textContent = binSettings.empty_at
        ? `Bin review reminder set for ${formatScheduleDate(binSettings.empty_at)}. Stash will remind you beforehand and again on that date. Nothing is deleted automatically.`
        : "No review reminder is set. Copies stay here until you restore them or choose to empty the Bin.";
    if (cancelButton) cancelButton.hidden = !binSettings.empty_at;
    updateSelectionControls();
}


function showChatWorkspace() {
    finderWorkspaceOpen = false;
    if (libraryWorkspace) libraryWorkspace.hidden = true;
    if (chatWorkspace) chatWorkspace.hidden = false;
    if (finderWorkspace) finderWorkspace.hidden = true;
    finderNavigation?.classList.remove("active");
    closeMobileSidebar();
}


function showFinderWorkspace() {
    if (!window.StashFinderFiles?.hasReadAccess()) return;
    finderWorkspaceOpen = true;
    if (libraryWorkspace) libraryWorkspace.hidden = true;
    if (chatWorkspace) chatWorkspace.hidden = true;
    if (finderWorkspace) finderWorkspace.hidden = false;
    document.querySelectorAll(".nav-item[data-type]").forEach(button => button.classList.remove("active"));
    binNavigation?.classList.remove("active");
    finderNavigation?.classList.add("active");
    closeMobileSidebar();
    window.StashFinderFiles.openCurrentDirectory();
}


finderNavigation?.addEventListener("click", showFinderWorkspace);

document.addEventListener("stash:finder-access-changed", event => {
    const hasReadAccess = event.detail?.granted === true;
    if (finderNavigation) finderNavigation.hidden = !hasReadAccess;
    if (!hasReadAccess && finderWorkspaceOpen) showLibraryWorkspace();
});


function setCopyMakerTheme(theme) {
    const selected = theme === "light" ? "light" : "dark";
    document.documentElement.dataset.theme = selected;
    const toggle = document.getElementById("themeToggle");
    const icon = document.getElementById("themeIcon");
    const label = document.getElementById("themeLabel");
    if (toggle) toggle.setAttribute("aria-label", `Switch to ${selected === "dark" ? "light" : "dark"} theme`);
    if (icon) icon.textContent = selected === "dark" ? "☼" : "◐";
    if (label) label.textContent = selected === "dark" ? "Light appearance" : "Dark appearance";
}


const savedTheme = localStorage.getItem("copyMakerTheme");
setCopyMakerTheme(savedTheme || (window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark"));

document.getElementById("themeToggle")?.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("copyMakerTheme", next);
    setCopyMakerTheme(next);
});

document.querySelectorAll(".mobile-menu-toggle").forEach(button => {
    button.addEventListener("click", () => {
        const opening = !sidebar?.classList.contains("mobile-open");
        sidebar?.classList.toggle("mobile-open", opening);
        if (sidebarOverlay) sidebarOverlay.hidden = !opening;
        document.querySelectorAll(".mobile-menu-toggle").forEach(item => {
            item.setAttribute("aria-expanded", String(opening));
            item.setAttribute("aria-label", opening ? "Close navigation" : "Open navigation");
        });
    });
});

sidebarOverlay?.addEventListener("click", closeMobileSidebar);


/* =========================================================
   HELPERS
========================================================= */

function escapeHtml(value) {

    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}


function formatSize(bytes) {

    const size =
        Number(bytes);

    if (!Number.isFinite(size) || size <= 0)
        return "";

    if (size < 1024)
        return `${size} B`;

    if (size < 1024 * 1024)
        return `${(size / 1024).toFixed(1)} KB`;

    if (size < 1024 * 1024 * 1024)
        return `${(size / (1024 * 1024)).toFixed(1)} MB`;

    return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}


function mediaUrl(item) {

    if (!item)
        return "";

    let candidate = item.url;

    if (!candidate && item.file)
        candidate = "/media/" + encodeURIComponent(item.file);

    if (!candidate && item.filename)
        candidate = "/media/" + encodeURIComponent(item.filename);

    if (typeof candidate !== "string" || !candidate)
        return "";

    try {
        const parsed = new URL(candidate, window.location.origin);
        if (
            parsed.origin !== window.location.origin ||
            !(/^\/media\//.test(parsed.pathname) || /^\/videos\//.test(parsed.pathname))
        ) {
            return "";
        }
        return parsed.href;
    } catch (error) {
        return "";
    }
}


function getItemType(item) {

    const raw =
        String(
            item?.type ||
            item?.media_type ||
            item?.kind ||
            ""
        ).toLowerCase();

    if (
        raw.includes("image") ||
        item?.mime_type?.startsWith("image/")
    )
        return "image";

    if (
        raw.includes("audio") ||
        item?.mime_type?.startsWith("audio/")
    )
        return "audio";

    if (
        raw.includes("video") ||
        item?.mime_type?.startsWith("video/")
    )
        return "video";

    if (
        raw.includes("file") ||
        item?.filename ||
        item?.original_name
    )
        return "file";

    return "text";
}


function getItemDate(item) {

    const raw =
        item?.created_at ||
        item?.timestamp ||
        item?.created ||
        item?.date;

    if (!raw)
        return null;

    const date =
        new Date(raw);

    if (Number.isNaN(date.getTime()))
        return null;

    return date;
}


function dateKey(date) {

    return [
        date.getFullYear(),
        String(date.getMonth() + 1).padStart(2, "0"),
        String(date.getDate()).padStart(2, "0")
    ].join("-");
}


function formatDateHeading(key) {

    if (key === "all")
        return "All dates";

    const parts =
        key.split("-").map(Number);

    const date =
        new Date(
            parts[0],
            parts[1] - 1,
            parts[2]
        );

    const today =
        new Date();

    const yesterday =
        new Date();

    yesterday.setDate(
        yesterday.getDate() - 1
    );

    if (
        dateKey(date) ===
        dateKey(today)
    )
        return "Today";

    if (
        dateKey(date) ===
        dateKey(yesterday)
    )
        return "Yesterday";

    return date.toLocaleDateString(
        undefined,
        {
            weekday: "long",
            month: "short",
            day: "numeric",
            year: "numeric"
        }
    );
}


function formatTime(date) {

    return date.toLocaleTimeString(
        undefined,
        {
            hour: "numeric",
            minute: "2-digit"
        }
    );
}


function formatFullDate(date) {

    return date.toLocaleString(
        undefined,
        {
            dateStyle: "medium",
            timeStyle: "short"
        }
    );
}


function formatScheduleDate(value) {

    if (!value)
        return "";

    const date =
        new Date(value);

    if (Number.isNaN(date.getTime()))
        return "";

    return formatFullDate(date);
}


function getSearchableText(item) {

    return JSON.stringify(item)
        .toLowerCase();
}


/* =========================================================
   CLIPBOARD
========================================================= */

async function loadClipboard() {

    try {

        const requests = [fetch("/api/clipboard"), fetch("/api/bin")];
        if (!foldersLoaded) requests.push(fetch("/api/folders"));
        const [response, binResponse, foldersResponse] = await Promise.all(requests);

        if (!response.ok)
            throw new Error(
                "API error: " +
                response.status
            );

        const data =
            await response.json();

        if (!Array.isArray(data))
            throw new Error(
                "API did not return an array"
            );

        allItems = data;

        if (foldersResponse?.ok) {
            const folderData = await foldersResponse.json();
            folders = Array.isArray(folderData.folders) ? folderData.folders : [];
            foldersLoaded = true;
        }

        if (binResponse.ok) {
            const binData = await binResponse.json();
            binItems = Array.isArray(binData.items) ? binData.items : [];
            binSettings = binData.settings || { empty_at: null, reminder_sent_for: null };
        }

        updateCounts();
        buildFolderNavigation();
        buildDateNavigation();
        syncDateJumpControls();
        updateBinControls();
        renderItems();

    } catch (error) {

        console.error(
            "Stash UI error:",
            error
        );

        allItems = [];
        binItems = [];

        if (resultSummary)
            resultSummary.textContent =
                "Error loading copies";

    }
}

document.addEventListener("copy-maker:clipboard-imported", loadClipboard);


/* =========================================================
   COUNTS
========================================================= */

function updateCounts() {

    const counts = {
        all: allItems.length,
        text: 0,
        image: 0,
        audio: 0,
        video: 0,
        file: 0
    };

    allItems.forEach(item => {

        const type =
            getItemType(item);

        counts[type]++;
    });

    const elements = {
        all: "countAll",
        text: "countText",
        image: "countImage",
        audio: "countAudio",
        video: "countVideo",
        file: "countFile"
    };

    Object.entries(elements).forEach(
        ([type, id]) => {

            const element =
                document.getElementById(id);

            if (element)
                element.textContent =
                    counts[type];

        }
    );

    const binCount = document.getElementById("countBin");
    if (binCount) binCount.textContent = String(binItems.length);
}


/* =========================================================
   DATE NAVIGATION
========================================================= */

function buildDateNavigation() {

    if (!dateNavigation)
        return;

    const currentItems = getActiveItems().filter(item =>
        activeView === "bin" || itemMatchesFolder(item, activeFolder)
    );
    const groups = new Map();

    currentItems.forEach(item => {

        const date = getActiveItemDate(item);

        if (!date)
            return;

        const key =
            dateKey(date);

        groups.set(
            key,
            (groups.get(key) || 0) + 1
        );

    });

    const dates =
        Array.from(groups.entries())
            .sort(
                (a, b) =>
                    b[0].localeCompare(a[0])
            );

    dateNavigation.innerHTML = "";

    const allButton =
        document.createElement("button");

    allButton.className =
        "date-item" +
        (activeDate === "all" && !activeTime
            ? " active"
            : "");

    allButton.innerHTML = `
        <span>All dates</span>
        <span class="date-count">
            ${currentItems.length}
        </span>
    `;

    allButton.onclick = () => {

        if (activeView !== "bin") showLibraryWorkspace();
        else closeMobileSidebar();

        activeDate = "all";
        activeTime = "";
        visibleLimit = PAGE_SIZE;

        syncDateJumpControls();
        buildDateNavigation();
        renderItems();
        if (filterDisclosure) filterDisclosure.open = false;

    };

    dateNavigation.appendChild(
        allButton
    );


    dates.slice(0, 14).forEach(
        ([key, count]) => {

            const button =
                document.createElement("button");

            button.className =
                "date-item" +
                (
                    activeDate === key
                        ? " active"
                        : ""
                );

            button.innerHTML = `
                <span>
                    ${escapeHtml(
                        formatDateHeading(key)
                    )}
                </span>

                <span class="date-count">
                    ${count}
                </span>
            `;

            button.onclick = () => {

                if (activeView !== "bin") showLibraryWorkspace();
                else closeMobileSidebar();

                activeDate = key;
                activeTime = "";
                visibleLimit = PAGE_SIZE;

                syncDateJumpControls();
                buildDateNavigation();
                renderItems();
                if (filterDisclosure) filterDisclosure.open = false;

            };

            dateNavigation.appendChild(
                button
            );

        }
    );
}


function itemMatchesFolder(item, folder = activeFolder) {
    if (folder === ALL_FOLDERS) return true;
    if (folder === null) return !item?.folder_name;
    return item?.folder_name === folder;
}


function buildFolderNavigation() {
    if (!folderNavigation) return;

    folderNavigation.innerHTML = "";
    const countFor = folder => allItems.filter(item => itemMatchesFolder(item, folder)).length;

    const appendFolder = (label, count, folder, { allowDrop = true } = {}) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "date-item folder-item" + (activeFolder === folder ? " active" : "");
        button._stashFolderTarget = folder;

        const name = document.createElement("span");
        name.className = "folder-item-name";
        name.textContent = label;
        const countLabel = document.createElement("span");
        countLabel.className = "date-count";
        countLabel.textContent = String(count);
        button.append(name, countLabel);

        button.addEventListener("click", () => selectFolder(folder));
        if (!allowDrop) button.dataset.dropDisabled = "true";
        folderNavigation.appendChild(button);
    };

    const unfiledCount = countFor(null);
    if (unfiledCount || activeFolder === null) appendFolder("Unfiled", unfiledCount, null);
    folders.forEach(folder => appendFolder(folder, countFor(folder), folder));
    if (!folders.length && !unfiledCount) {
        const empty = document.createElement("p");
        empty.className = "folder-empty-state";
        empty.textContent = "Create a folder to group copies.";
        folderNavigation.appendChild(empty);
    }

    if (moveFolderSelect) {
        const previousValue = moveFolderSelect.value;
        moveFolderSelect.innerHTML = "<option value=\"\">Choose folder…</option>";
        const unfiled = document.createElement("option");
        unfiled.value = "__stash_unfiled__";
        unfiled.textContent = "Unfiled";
        moveFolderSelect.appendChild(unfiled);
        folders.forEach(folder => {
            const option = document.createElement("option");
            option.value = `folder:${folder}`;
            option.textContent = folder;
            moveFolderSelect.appendChild(option);
        });
        const optionStillExists = Array.from(moveFolderSelect.options).some(option => option.value === previousValue);
        moveFolderSelect.value = optionStillExists ? previousValue : "";
    }

    updateSelectionControls();
}


function selectFolder(folder) {
    if (activeView === "bin" || finderWorkspaceOpen) showLibraryWorkspace();
    else closeMobileSidebar();

    activeFolder = folder;
    activeDate = "all";
    activeTime = "";
    activeType = "all";
    activeWorkspaceMode = "all";
    selectedItemIds.clear();
    visibleLimit = PAGE_SIZE;
    if (searchInput) searchInput.value = "";
    updateSearchUI();

    document.querySelectorAll(".nav-item[data-type]").forEach(button => {
        button.classList.toggle("active", button.dataset.type === "all");
    });
    document.querySelectorAll(".filter-button").forEach(button => {
        button.classList.toggle(
            "active",
            button.dataset.mode ? button.dataset.mode === "all" : button.dataset.filter === "all"
        );
    });

    syncDateJumpControls();
    updateViewChrome();
    buildFolderNavigation();
    buildDateNavigation();
    renderItems();
}


function syncDateJumpControls(statusText) {
    if (dateJumpInput && document.activeElement !== dateJumpInput) {
        dateJumpInput.value = activeDate === "all" ? "" : activeDate;
    }
    if (timeJumpInput && document.activeElement !== timeJumpInput) {
        timeJumpInput.value = activeTime;
    }
    if (dateJumpStatus) {
        const defaultStatus = activeDate !== "all" && activeTime
            ? `Showing copies from ${activeDate} at ${activeTime}.`
            : activeDate !== "all"
                ? `Showing copies from ${activeDate}.`
                : activeTime
                    ? `Showing copies from ${activeTime} on any date.`
                    : "Choose a date or time.";
        dateJumpStatus.textContent = statusText || defaultStatus;
    }
    updateFilterSummary();
}


function updateFilterSummary() {
    if (!filterSummaryText) return;
    const activeFilters = Number(activeType !== "all" || activeWorkspaceMode !== "all") + Number(activeDate !== "all" || Boolean(activeTime));
    filterSummaryText.textContent = activeFilters
        ? `${activeFilters} ${activeFilters === 1 ? "filter" : "filters"}`
        : "Filter";
    filterDisclosure?.querySelector("summary")?.setAttribute(
        "aria-label",
        activeFilters ? `${activeFilters} active ${activeFilters === 1 ? "filter" : "filters"}` : "Open filters"
    );
    filterDisclosure?.classList.toggle("has-active-filters", activeFilters > 0);
}


/* =========================================================
   FILTERING
========================================================= */

function getFilteredItems() {

    const query =
        searchInput
            ? searchInput.value
                .trim()
                .toLowerCase()
            : "";

    let items =
        getActiveItems().filter(item => {

            if (activeView !== "bin" && !itemMatchesFolder(item, activeFolder))
                return false;

            const type =
                getItemType(item);

            if (
                activeType !== "all" &&
                type !== activeType
            )
                return false;

            if (
                activeWorkspaceMode !== "all" &&
                item.workspace_mode !== activeWorkspaceMode
            )
                return false;

            if (activeDate !== "all") {

                const date = getActiveItemDate(item);

                if (!date)
                    return false;

                if (
                    dateKey(date) !==
                    activeDate
                )
                    return false;
            }

            if (activeTime) {
                const date = getActiveItemDate(item);
                const [hours, minutes] = activeTime.split(":").map(Number);
                if (!date || date.getHours() !== hours || date.getMinutes() !== minutes)
                    return false;
            }

            if (query) {

                if (
                    !getSearchableText(item)
                        .includes(query)
                )
                    return false;
            }

            return true;

        });

    items.sort(
        (a, b) => {

            const da =
                getActiveItemDate(a)?.getTime() || 0;

            const db =
                getActiveItemDate(b)?.getTime() || 0;

            return sortNewestFirst
                ? db - da
                : da - db;

        }
    );

    return items;
}


/* =========================================================
   RENDER
========================================================= */

function renderItems() {

    if (!grid)
        return;

    const filtered =
        getFilteredItems();

    const visible =
        filtered.slice(
            0,
            visibleLimit
        );

    grid.innerHTML = "";

    const emptyHeading = emptyState?.querySelector("h2");
    const emptyDescription = emptyState?.querySelector("p");
    if (emptyHeading) {
        emptyHeading.textContent = activeView === "bin"
            ? "Your Bin is empty"
            : allItems.length === 0
                ? "Nothing saved yet"
                : "No matching copies";
    }
    if (emptyDescription) {
        emptyDescription.textContent = activeView === "bin"
            ? "Move a copy to the Bin and you’ll find it here."
            : allItems.length === 0
                ? "Copy text, a link, or a file. Stash saves it here automatically."
                : "Try another search or clear a filter.";
    }

    if (!filtered.length) {

        emptyState.hidden = false;

        if (loadMoreContainer)
            loadMoreContainer.hidden = true;

        updateSummary(
            filtered.length
        );
        updateSelectionControls();

        return;

    }

    emptyState.hidden = true;

    const groups =
        groupByDateAndTime(visible);

    groups.forEach(
        (dateGroup) => {

            const groupElement =
                document.createElement("section");

            groupElement.className =
                "date-group";

            groupElement.innerHTML = `
                <div class="date-group-header">

                    <span class="date-group-title">
                        ${escapeHtml(
                            formatDateHeading(
                                dateGroup.key
                            )
                        )}
                    </span>

                    <span class="date-group-count">
                        ${dateGroup.items.length}
                        shown
                    </span>

                </div>
            `;

            dateGroup.timeGroups.forEach(
                timeGroup => {

                    const timeElement =
                        document.createElement(
                            "div"
                        );

                    timeElement.className =
                        "time-group";

                    timeElement.innerHTML = `
                        <div class="time-group-header">

                            <span class="time-dot"></span>

                            <span>
                                ${escapeHtml(
                                    timeGroup.label
                                )}
                            </span>

                            <span class="time-count">
                                ${timeGroup.items.length}
                                copies
                            </span>

                        </div>
                    `;

                    timeGroup.items.forEach(
                        item => {

                            timeElement.appendChild(
                                createRow(item)
                            );

                        }
                    );

                    groupElement.appendChild(
                        timeElement
                    );

                }
            );

            grid.appendChild(
                groupElement
            );

        }
    );


    if (loadMoreContainer) {

        loadMoreContainer.hidden =
            visible.length >= filtered.length;

    }

    updateSummary(
        filtered.length,
        visible.length
    );
    updateSelectionControls();
}


function suggestedFolderForItem(item) {
    if (!item || item.folder_name || item.trashed_at) return null;

    const type = getItemType(item);
    const filename = String(item.original_name || item.filename || item.name || "");
    const extension = filename.split("?")[0].split(".").pop()?.toLowerCase() || "";
    const content = String(item.content || item.text || item.url || item.source_url || "");
    const mode = String(item.workspace_mode || "").toLowerCase();
    const codeExtensions = new Set([
        "py", "pyw", "js", "jsx", "ts", "tsx", "html", "htm", "css", "scss",
        "json", "yaml", "yml", "sh", "bash", "zsh", "sql", "java", "kt", "go",
        "rs", "c", "h", "cpp", "hpp", "cs", "php", "rb", "swift", "dart",
        "vue", "svelte", "xml", "toml", "ipynb",
    ]);
    const documentExtensions = new Set([
        "pdf", "doc", "docx", "rtf", "txt", "md", "pages", "odt", "xls", "xlsx",
        "csv", "ppt", "pptx", "key", "epub",
    ]);

    let name = "Notes";
    if (type === "video") name = "Videos";
    else if (type === "image") name = "Images";
    else if (type === "audio") name = "Audio";
    else if (type === "file" && codeExtensions.has(extension)) name = "Code";
    else if (type === "file" && documentExtensions.has(extension)) name = "Documents";
    else if (type === "file") name = "Files";
    else if (/https?:\/\//i.test(content)) name = "Links";
    else if (mode === "developer") name = "Code";
    else if (mode === "student") name = "Study";

    const aliases = {
        Videos: ["video", "videos", "clip", "clips", "movie", "movies"],
        Images: ["image", "images", "photo", "photos", "picture", "pictures", "screenshot", "screenshots"],
        Audio: ["audio", "music", "podcast", "podcasts", "sound"],
        Files: ["file", "files", "download", "downloads"],
        Documents: ["document", "documents", "doc", "docs", "pdf", "reading"],
        Code: ["code", "developer", "development", "programming", "script", "scripts", "source"],
        Links: ["link", "links", "bookmark", "bookmarks", "website", "websites", "article", "articles"],
        Study: ["study", "student", "school", "class", "learning", "lecture", "lectures"],
        Notes: ["note", "notes", "text", "writing"],
    }[name];
    const folderTokens = folder => String(folder).toLowerCase().match(/[a-z0-9]+/g) || [];
    const existing = folders.find(folder => {
        const tokens = folderTokens(folder);
        return aliases.some(alias => tokens.includes(alias));
    });
    return { name: existing || name, create: !existing };
}


async function fileCopyIntoSuggestedFolder(itemId, folderName, createFolder, button) {
    if (!Number.isFinite(Number(itemId)) || !folderName) return;
    button.disabled = true;
    const previousLabel = button.textContent;
    button.textContent = createFolder ? "Creating…" : "Filing…";
    try {
        let destination = folders.find(folder => folder === folderName);
        if (!destination) {
            const response = await fetch("/api/folders", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: folderName }),
            });
            const result = await response.json().catch(() => ({}));
            if (response.status === 401 || result.error === "login_required") {
                throw new Error("Sign in to Stash and try again.");
            }
            if (!response.ok || !result.success) {
                throw new Error(result.error || "Stash could not create the suggested folder.");
            }
            folders = Array.isArray(result.folders) ? result.folders : folders;
            foldersLoaded = true;
            destination = folders.find(folder => folder.toLowerCase() === folderName.toLowerCase());
        }
        if (!destination) throw new Error("That folder is no longer available.");

        const result = await requestBinAction("/api/folders/move", {
            item_ids: [Number(itemId)],
            folder_name: destination,
        });
        const item = allItems.find(copy => Number(copy.id) === Number(itemId));
        if (item) item.folder_name = destination;
        updateCounts();
        buildFolderNavigation();
        renderItems();
        showStashNotification(`Filed in ${destination}.`);
    } catch (error) {
        button.disabled = false;
        button.textContent = previousLabel;
        showStashNotification(error.message || "Stash could not file this copy.");
    }
}


/* =========================================================
   GROUPING
========================================================= */

function groupByDateAndTime(items) {

    const dateMap =
        new Map();

    items.forEach(item => {

        const date = getActiveItemDate(item);

        if (!date)
            return;

        const dKey =
            dateKey(date);

        if (!dateMap.has(dKey)) {

            dateMap.set(
                dKey,
                {
                    key: dKey,
                    items: [],
                    times: new Map()
                }
            );

        }

        const group =
            dateMap.get(dKey);

        group.items.push(item);

        const hourKey =
            [
                date.getHours(),
                String(
                    date.getMinutes()
                ).padStart(2, "0")
            ].join(":");

        if (!group.times.has(hourKey)) {

            group.times.set(
                hourKey,
                []
            );

        }

        group.times
            .get(hourKey)
            .push(item);

    });


    return Array.from(
        dateMap.values()
    ).map(group => {

        const timeGroups =
            Array.from(
                group.times.entries()
            )
            .sort(
                (a, b) =>
                    sortNewestFirst
                        ? b[0].localeCompare(a[0])
                        : a[0].localeCompare(b[0])
            )
            .map(
                ([label, items]) => ({
                    label,
                    items
                })
            );

        return {
            key: group.key,
            items: group.items,
            timeGroups
        };

    });

}


/* =========================================================
   COPY ROW
========================================================= */

function createRow(item) {

    const row =
        document.createElement("article");

    row.className =
        "copy-row";

    row._copyMakerItem =
        item;
    if (selectedItemIds.has(Number(item.id))) row.classList.add("copy-row-selected");


    const type =
        getItemType(item);

    const captureStatusLabels = {
        downloading: "Downloading original video…",
        capturing: "Capturing from the page…",
        saving: "Saving to Stash…",
    };
    const captureStatus = captureStatusLabels[item.capture_status] || "";
    const pendingCapture = Boolean(captureStatus);
    row.draggable = activeView === "library" && !pendingCapture;
    const folderSuggestion = activeView === "library" && !pendingCapture
        ? suggestedFolderForItem(item)
        : null;

    const date =
        getActiveItemDate(item);

    const typeLabels = {
        text: "Text",
        image: "Image",
        audio: "Audio",
        video: "Video",
        file: "File"
    };

    const typeIcons = {
        text: "T",
        image: "□",
        audio: "♫",
        video: "▶",
        file: "□"
    };


    let title = "";
    let preview = "";


    if (type === "text") {

        const text =
            String(
                item.text ||
                item.content ||
                item.value ||
                ""
            );

        title =
            text
                .split("\n")[0]
                .slice(0, 100)
                || "Text copy";

        preview =
            text
                .replace(/\s+/g, " ")
                .slice(0, 180);

    } else if (type === "file") {

        title =
            item.original_name ||
            item.filename ||
            item.name ||
            "File";

        preview =
            formatSize(
                item.size ||
                item.file_size
            );

    } else if (type === "video") {

        title =
            item.original_name ||
            item.filename ||
            "Video copy";

        preview = pendingCapture
            ? captureStatus
            : formatSize(item.size) || "Saved video";

    } else {

        title =
            item.name ||
            item.original_name ||
            `${typeLabels[type]} copy`;

        preview =
            item.url ||
            item.source_url ||
            item.filename ||
            "";
    }


    let thumbnail =
        "";

    if (
        type === "image" &&
        mediaUrl(item)
    ) {

        thumbnail = `
            <img
                class="copy-thumbnail"
                src="${escapeHtml(
                    mediaUrl(item)
                )}"
                alt=""
                loading="lazy"
            >
        `;

        row.classList.add(
            "has-media"
        );

    }

    if (
        type === "video" &&
        mediaUrl(item)
    ) {

        thumbnail = `
            <button
                class="copy-video-preview"
                type="button"
                aria-label="Play ${escapeHtml(title)} in Stash"
            >
                <span class="copy-video-play-icon" aria-hidden="true">▶</span>
                <span>Play in Stash</span>
            </button>
        `;

        row.classList.add(
            "has-video-preview"
        );

    }


    row.innerHTML = `

        <label class="copy-select-wrap" aria-label="Select ${escapeHtml(title)}">
            <input
                class="copy-select-toggle"
                type="checkbox"
                data-copy-select="${escapeHtml(item.id)}"
                ${selectedItemIds.has(Number(item.id)) ? "checked" : ""}
                ${pendingCapture ? "disabled" : ""}
                aria-label="Select ${escapeHtml(title)}"
            >
            <span aria-hidden="true"></span>
        </label>

        <div class="copy-icon">

            ${
                thumbnail
                    ? thumbnail
                    : escapeHtml(
                        typeIcons[type]
                    )
            }

        </div>


        <div class="copy-main">

            <div class="copy-title">
                ${escapeHtml(title)}
            </div>

            <div class="copy-preview">
                ${escapeHtml(
                    preview
                )}
            </div>

            ${folderSuggestion ? `
                <div class="copy-folder-suggestion">
                    <span>Suggested: <strong>${escapeHtml(folderSuggestion.name)}</strong></span>
                    <button class="copy-folder-suggestion-action" type="button" data-folder-suggestion="${escapeHtml(folderSuggestion.name)}" data-create-folder="${folderSuggestion.create ? "true" : "false"}" aria-label="${folderSuggestion.create ? "Create and file in" : "File in"} ${escapeHtml(folderSuggestion.name)}">${folderSuggestion.create ? "Create folder" : "File here"}</button>
                </div>
            ` : ""}

        </div>


        <div class="copy-meta">

            <span class="type-badge">
                ${escapeHtml(
                    typeLabels[type]
                )}
            </span>

            ${item.folder_name && activeView !== "bin" ? `
                <span class="copy-folder-badge" title="Saved in ${escapeHtml(item.folder_name)}">${escapeHtml(item.folder_name)}</span>
            ` : ""}

            <span>
                ${
                    date
                        ? escapeHtml(
                            formatTime(date)
                        )
                        : ""
                }
            </span>

            ${activeView === "bin" ? `
                <button class="bin-row-restore" data-bin-restore="${escapeHtml(item.id)}" type="button">Restore</button>
            ` : ""}

        </div>

    `;

    if (pendingCapture) {
        row.classList.add("copy-row-pending");
    }

    const folderSuggestionButton = row.querySelector(".copy-folder-suggestion-action");
    folderSuggestionButton?.addEventListener("click", event => {
        event.stopPropagation();
        fileCopyIntoSuggestedFolder(
            item.id,
            folderSuggestionButton.dataset.folderSuggestion,
            folderSuggestionButton.dataset.createFolder === "true",
            folderSuggestionButton,
        );
    });

    return row;
}


/* =========================================================
   SUMMARY
========================================================= */

function updateSummary(
    total,
    visible = total
) {

    if (!resultSummary)
        return;

    if (total === visible) {

        resultSummary.textContent =
            `${total} ${total === 1 ? "copy" : "copies"}`;

    } else {

        resultSummary.textContent =
            `${visible} of ${total} copies`;

    }
}


/* =========================================================
   SEARCH
========================================================= */

function updateSearchUI() {

    const hasText =
        Boolean(
            searchInput?.value
        );

    if (clearSearch) {

        clearSearch.classList.toggle(
            "visible",
            hasText
        );

    }

}


searchInput?.addEventListener(
    "input",
    () => {

        visibleLimit = PAGE_SIZE;

        updateSearchUI();
        renderItems();

    }
);


clearSearch?.addEventListener(
    "click",
    () => {

        searchInput.value = "";

        updateSearchUI();
        renderItems();

        searchInput.focus();

    }
);


/* =========================================================
   SEARCH SHORTCUT
========================================================= */

document.addEventListener(
    "keydown",
    event => {

        if (
            (event.metaKey || event.ctrlKey) &&
            event.key.toLowerCase() === "k"
        ) {

            event.preventDefault();
            searchInput?.focus();
            searchInput?.select();

        }

        if (
            event.key === "Escape" &&
            copyViewer &&
            !copyViewer.hidden
        ) {

            closeViewer();

        }

        if (event.key === "Escape" && filterDisclosure?.open) {
            filterDisclosure.open = false;
            document.getElementById("filterSummary")?.focus();
        }

    }
);

/* UI-FIX-4: dismiss the filter popover when a pointer lands outside it. */
document.addEventListener("pointerdown", event => {
    if (!filterDisclosure?.open || filterDisclosure.contains(event.target)) return;
    filterDisclosure.open = false;
});


/* =========================================================
   TYPE FILTERS
========================================================= */

document
    .querySelectorAll(
        ".filter-button"
    )
    .forEach(button => {

        button.addEventListener(
                "click",
                () => {

                showLibraryWorkspace();

                activeWorkspaceMode =
                    button.dataset.mode || "all";

                activeType = activeWorkspaceMode === "all"
                    ? (button.dataset.filter || "all")
                    : "all";

                visibleLimit =
                    PAGE_SIZE;

                document
                    .querySelectorAll(
                        ".filter-button"
                    )
                    .forEach(
                        b =>
                            b.classList.remove(
                                "active"
                            )
                    );

                button.classList.add(
                    "active"
                );

                updateFilterSummary();

                document
                    .querySelectorAll(
                        ".nav-item[data-type]"
                    )
                    .forEach(
                        nav => {

                            nav.classList.toggle(
                                "active",
                                activeWorkspaceMode === "all" &&
                                nav.dataset.type === activeType
                            );

                        }
                    );

                renderItems();

            }
        );

    });


/* =========================================================
   SIDEBAR FILTERS
========================================================= */

document
    .querySelectorAll(
        ".nav-item[data-type]"
    )
    .forEach(button => {

        button.addEventListener(
            "click",
            () => {

                showLibraryWorkspace();

            activeType =
                    button.dataset.type;

                if (activeType === "all") {
                    activeFolder = ALL_FOLDERS;
                    activeDate = "all";
                    activeTime = "";
                    syncDateJumpControls();
                    buildFolderNavigation();
                    buildDateNavigation();
                }

                activeWorkspaceMode = "all";
                updateFilterSummary();

                visibleLimit =
                    PAGE_SIZE;

                document
                    .querySelectorAll(
                        ".nav-item[data-type]"
                    )
                    .forEach(
                        item =>
                            item.classList.remove(
                                "active"
                            )
                    );

                button.classList.add(
                    "active"
                );

                document
                    .querySelectorAll(
                        ".filter-button"
                    )
                    .forEach(
                        filter => {

                            filter.classList.toggle(
                                "active",
                                filter.dataset.mode
                                    ? filter.dataset.mode === activeWorkspaceMode
                                    : activeWorkspaceMode === "all" &&
                                      filter.dataset.filter === activeType
                            );

                        }
                    );

                updateViewChrome();
                renderItems();

            }
        );

    });


binNavigation?.addEventListener("click", showBinWorkspace);

document.getElementById("newFolderButton")?.addEventListener("click", () => {
    const dialog = document.getElementById("folderDialog");
    const input = document.getElementById("folderNameInput");
    const status = document.getElementById("folderFormStatus");
    if (status) status.textContent = "";
    if (dialog?.showModal) {
        dialog.showModal();
        window.setTimeout(() => input?.focus(), 0);
    }
});

document.getElementById("closeFolderDialog")?.addEventListener("click", () => {
    document.getElementById("folderDialog")?.close();
});

document.getElementById("cancelFolderButton")?.addEventListener("click", () => {
    document.getElementById("folderDialog")?.close();
});

document.getElementById("folderForm")?.addEventListener("submit", async event => {
    event.preventDefault();
    const input = document.getElementById("folderNameInput");
    const status = document.getElementById("folderFormStatus");
    const submit = document.getElementById("saveFolderButton");
    const name = input?.value.trim();
    if (!name) {
        input?.reportValidity();
        return;
    }

    if (submit) submit.disabled = true;
    if (status) status.textContent = "Creating folder…";
    try {
        const response = await fetch("/api/folders", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name })
        });
        const result = await response.json().catch(() => ({}));
        if (response.status === 401 || result.error === "login_required") {
            throw new Error("Sign in to Stash and try again.");
        }
        if (!response.ok || !result.success) {
            throw new Error(result.error || `Stash returned HTTP ${response.status}.`);
        }

        folders = Array.isArray(result.folders) ? result.folders : folders;
        foldersLoaded = true;
        document.getElementById("folderDialog")?.close();
        if (input) input.value = "";
        selectFolder(name);
        showStashNotification(`Created the ${name} folder.`);
    } catch (error) {
        if (status) status.textContent = error.message;
    } finally {
        if (submit) submit.disabled = false;
    }
});

dateJumpForm?.addEventListener("submit", event => {
    event.preventDefault();
    const date = dateJumpInput?.value || "";
    const time = timeJumpInput?.value || "";
    if (!date && !time) {
        if (dateJumpStatus) dateJumpStatus.textContent = "Choose a date or time.";
        dateJumpInput?.focus();
        return;
    }

    activeDate = date || "all";
    activeTime = time;
    visibleLimit = PAGE_SIZE;
    const description = date && time
        ? `Showing copies from ${date} at ${time}.`
        : date
            ? `Showing copies from ${date}.`
            : `Showing copies from ${time} on any date.`;
    syncDateJumpControls(description);
    buildDateNavigation();
    renderItems();
    if (filterDisclosure) filterDisclosure.open = false;
});

document.getElementById("dateJumpClearButton")?.addEventListener("click", () => {
    activeDate = "all";
    activeTime = "";
    visibleLimit = PAGE_SIZE;
    if (dateJumpInput) dateJumpInput.value = "";
    if (timeJumpInput) timeJumpInput.value = "";
    syncDateJumpControls();
    buildDateNavigation();
    renderItems();
});

function toggleSelectionOfFilteredItems() {
    const items = getFilteredItems();
    const allSelected = items.length > 0 && items.every(item => selectedItemIds.has(Number(item.id)));
    items.forEach(item => {
        const id = Number(item.id);
        if (allSelected) selectedItemIds.delete(id);
        else selectedItemIds.add(id);
    });
    renderItems();
}

document.getElementById("selectAllButton")?.addEventListener("click", toggleSelectionOfFilteredItems);
document.getElementById("selectAllBinButton")?.addEventListener("click", toggleSelectionOfFilteredItems);

grid?.addEventListener("change", event => {
    const checkbox = event.target.closest("[data-copy-select]");
    if (!checkbox) return;
    const id = Number(checkbox.dataset.copySelect);
    if (!Number.isFinite(id)) return;
    if (checkbox.checked) selectedItemIds.add(id);
    else selectedItemIds.delete(id);
    checkbox.closest(".copy-row")?.classList.toggle("copy-row-selected", checkbox.checked);
    updateSelectionControls();
});

function setDeviceTransferDialogStatus(message, kind = "") {
    if (!deviceTransferDialogStatus) return;
    deviceTransferDialogStatus.textContent = message;
    deviceTransferDialogStatus.classList.toggle("is-error", kind === "error");
    deviceTransferDialogStatus.classList.toggle("is-success", kind === "success");
}

function openDeviceTransferDialog() {
    if (!selectedItemIds.size || activeView === "bin" || !deviceTransferDialog) return;
    deviceTransferForm?.reset();
    if (deviceTransferProgress) deviceTransferProgress.hidden = true;
    if (deviceTransferProgressBar) deviceTransferProgressBar.value = 0;
    if (deviceTransferStartButton) {
        deviceTransferStartButton.hidden = false;
        deviceTransferStartButton.disabled = false;
        deviceTransferStartButton.textContent = "Send copies";
    }
    deviceTransferCloseButtons.forEach(button => {
        if (button) button.disabled = false;
    });
    setDeviceTransferDialogStatus(`${selectedItemIds.size} ${selectedItemIds.size === 1 ? "copy is" : "copies are"} selected.`);
    deviceTransferDialog.showModal();
}

function waitForDeviceTransferPoll() {
    return new Promise(resolve => window.setTimeout(resolve, 600));
}

async function monitorDeviceTransfer(jobId) {
    while (true) {
        await waitForDeviceTransferPoll();
        const response = await fetch(`/api/device-transfer/status/${encodeURIComponent(jobId)}`, {
            cache: "no-store",
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || !result.success) {
            throw new Error(result.error || "Stash could not read the transfer progress.");
        }
        const job = result;
        const totalBytes = Number(job.total_bytes) || 0;
        const sentBytes = Number(job.sent_bytes) || 0;
        const itemCount = Number(job.item_count) || 0;
        const completedItems = Number(job.completed_items) || 0;
        const percent = totalBytes > 0
            ? Math.min(99, Math.floor((sentBytes / totalBytes) * 100))
            : itemCount > 0 ? Math.min(99, Math.floor((completedItems / itemCount) * 100)) : 0;
        if (deviceTransferProgressBar) deviceTransferProgressBar.value = percent;
        if (deviceTransferProgressText) {
            deviceTransferProgressText.textContent = job.message || "Sending copies…";
        }
        if (job.status === "complete") {
            if (deviceTransferProgressBar) deviceTransferProgressBar.value = 100;
            if (deviceTransferProgressText) deviceTransferProgressText.textContent = job.message || "Copies saved on the receiving laptop.";
            return;
        }
        if (job.status === "error") {
            throw new Error(job.error || "Stash could not finish sending the selected copies.");
        }
    }
}

sendSelectedCopiesButton?.addEventListener("click", openDeviceTransferDialog);
deviceTransferCloseButtons.forEach(button => {
    button?.addEventListener("click", () => {
        if (!deviceTransferInProgress) deviceTransferDialog?.close();
    });
});
deviceTransferDialog?.addEventListener("cancel", event => {
    if (deviceTransferInProgress) event.preventDefault();
});

deviceTransferForm?.addEventListener("submit", async event => {
    event.preventDefault();
    if (!selectedItemIds.size || deviceTransferInProgress) return;
    const receiverUrl = deviceTransferReceiverUrl?.value.trim() || "";
    const code = (deviceTransferPairCode?.value || "").trim().toUpperCase();
    if (!/^[A-F0-9]{8}$/.test(code)) {
        setDeviceTransferDialogStatus("Enter the 8-character one-time code shown in the receiving Stash.", "error");
        deviceTransferPairCode?.focus();
        return;
    }

    deviceTransferInProgress = true;
    if (deviceTransferStartButton) deviceTransferStartButton.disabled = true;
    deviceTransferCloseButtons.forEach(button => {
        if (button) button.disabled = true;
    });
    if (deviceTransferProgress) deviceTransferProgress.hidden = false;
    if (deviceTransferProgressBar) deviceTransferProgressBar.value = 0;
    if (deviceTransferProgressText) deviceTransferProgressText.textContent = "Connecting to the receiving laptop…";
    setDeviceTransferDialogStatus("Keep both laptops awake and on the same Wi-Fi until the transfer finishes.");

    let jobStarted = false;
    try {
        const response = await fetch("/api/device-transfer/send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                receiver_url: receiverUrl,
                code,
                item_ids: Array.from(selectedItemIds),
            }),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || !result.job_id) {
            throw new Error(result.error || "Stash could not start this transfer.");
        }
        jobStarted = true;
        await monitorDeviceTransfer(result.job_id);
        if (deviceTransferProgressBar) deviceTransferProgressBar.value = 100;
        if (deviceTransferStartButton) deviceTransferStartButton.hidden = true;
        deviceTransferCloseButtons.forEach(button => {
            if (button) button.disabled = false;
        });
        setDeviceTransferDialogStatus("Transfer complete. The copies are now in the receiving Stash library.", "success");
    } catch (error) {
        setDeviceTransferDialogStatus(
            jobStarted
                ? `${error.message} Create a new receive code before trying again.`
                : (error.message || "Stash could not start this transfer."),
            "error",
        );
        if (jobStarted) {
            if (deviceTransferStartButton) deviceTransferStartButton.hidden = true;
        } else if (deviceTransferStartButton) {
            deviceTransferStartButton.disabled = false;
        }
        deviceTransferCloseButtons.forEach(button => {
            if (button) button.disabled = false;
        });
    } finally {
        deviceTransferInProgress = false;
    }
});

document.getElementById("moveToBinButton")?.addEventListener("click", () => {
    moveItemsToBin(Array.from(selectedItemIds));
});

moveFolderSelect?.addEventListener("change", updateSelectionControls);

document.getElementById("moveToFolderButton")?.addEventListener("click", () => {
    if (!moveFolderSelect?.value) return;
    const folderName = moveFolderSelect.value === "__stash_unfiled__"
        ? null
        : moveFolderSelect.value.slice("folder:".length);
    moveItemsToFolder(Array.from(selectedItemIds), folderName);
});

document.getElementById("restoreSelectedButton")?.addEventListener("click", () => {
    restoreBinItems(Array.from(selectedItemIds));
});

document.getElementById("saveBinScheduleButton")?.addEventListener("click", () => {
    if (!binEmptyAt?.value) {
        alert("Choose a date and time for the Bin review reminder.");
        return;
    }
    const selectedDate = new Date(binEmptyAt.value);
    if (selectedDate <= new Date()) {
        alert("Choose a future date and time.");
        return;
    }
    saveBinSchedule(selectedDate.toISOString());
});

document.getElementById("cancelBinScheduleButton")?.addEventListener("click", () => {
    saveBinSchedule(null);
});

document.getElementById("emptyBinButton")?.addEventListener("click", async () => {
    if (!binItems.length) return;
    const confirmed = window.confirm(`Permanently delete all ${binItems.length} ${binItems.length === 1 ? "copy" : "copies"} in the Bin? This cannot be undone.`);
    if (!confirmed) return;
    try {
        const result = await requestBinAction("/api/bin/empty", {});
        selectedItemIds.clear();
        showStashNotification(`Permanently deleted ${result.deleted_count} ${result.deleted_count === 1 ? "copy" : "copies"} from the Bin.`);
        await loadClipboard();
    } catch (error) {
        alert(`Could not empty the Bin: ${error.message}`);
    }
});

grid?.addEventListener("dragstart", event => {
    const row = event.target.closest(".copy-row");
    if (!row || activeView !== "library") return;
    const draggedId = Number(row._copyMakerItem?.id);
    const ids = selectedItemIds.has(draggedId) ? Array.from(selectedItemIds) : [draggedId];
    event.dataTransfer?.setData("application/x-stash-item-ids", JSON.stringify(ids));
    event.dataTransfer?.setData("text/plain", JSON.stringify(ids));
    if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
});

binNavigation?.addEventListener("dragover", event => {
    event.preventDefault();
    binNavigation.classList.add("bin-drop-target");
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
});

binNavigation?.addEventListener("dragleave", () => binNavigation.classList.remove("bin-drop-target"));

binNavigation?.addEventListener("drop", event => {
    event.preventDefault();
    binNavigation.classList.remove("bin-drop-target");
    try {
        const raw = event.dataTransfer?.getData("application/x-stash-item-ids") || event.dataTransfer?.getData("text/plain");
        const ids = JSON.parse(raw || "[]");
        if (Array.isArray(ids) && ids.length) moveItemsToBin(ids.map(Number));
    } catch {
        // Ignore unrelated dragged content.
    }
});

folderNavigation?.addEventListener("dragover", event => {
    const target = event.target.closest(".folder-item");
    if (!target || target.dataset.dropDisabled === "true") return;
    event.preventDefault();
    target.classList.add("drag-over");
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
});

folderNavigation?.addEventListener("dragleave", event => {
    event.target.closest(".folder-item")?.classList.remove("drag-over");
});

folderNavigation?.addEventListener("drop", event => {
    const target = event.target.closest(".folder-item");
    if (!target || target.dataset.dropDisabled === "true") return;
    event.preventDefault();
    target.classList.remove("drag-over");
    try {
        const raw = event.dataTransfer?.getData("application/x-stash-item-ids") || event.dataTransfer?.getData("text/plain");
        const ids = JSON.parse(raw || "[]");
        if (Array.isArray(ids) && ids.length) {
            moveItemsToFolder(ids.map(Number), target._stashFolderTarget);
        }
    } catch {
        // Ignore unrelated dragged content.
    }
});


async function requestBinAction(url, body) {
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
    });
    const result = await response.json().catch(() => ({}));
    if (response.status === 401 || result.error === "login_required") throw new Error("Sign in to Stash and try again.");
    if (!response.ok || !result.success) throw new Error(result.error || `Stash returned HTTP ${response.status}.`);
    return result;
}


async function moveItemsToBin(ids) {
    const itemIds = [...new Set(ids.map(Number).filter(Number.isFinite))];
    if (!itemIds.length) return;
    try {
        const result = await requestBinAction("/api/bin/move", { item_ids: itemIds });
        selectedItemIds.clear();
        showStashNotification(`Moved ${result.moved_count} ${result.moved_count === 1 ? "copy" : "copies"} to the Bin. You can restore them until the Bin is emptied.`);
        await loadClipboard();
    } catch (error) {
        alert(`Could not move copies to the Bin: ${error.message}`);
    }
}


async function moveItemsToFolder(ids, folderName) {
    const itemIds = [...new Set(ids.map(Number).filter(Number.isFinite))];
    if (!itemIds.length) return;
    try {
        const result = await requestBinAction("/api/folders/move", {
            item_ids: itemIds,
            folder_name: folderName
        });
        selectedItemIds.clear();
        activeFolder = folderName === null ? null : folderName;
        activeDate = "all";
        activeTime = "";
        visibleLimit = PAGE_SIZE;
        syncDateJumpControls();
        updateViewChrome();
        buildFolderNavigation();
        buildDateNavigation();
        await loadClipboard();
        showStashNotification(`Moved ${result.moved_count} ${result.moved_count === 1 ? "copy" : "copies"} to ${folderName || "Unfiled"}.`);
    } catch (error) {
        alert(`Could not move copies to the folder: ${error.message}`);
    }
}


async function restoreBinItems(ids) {
    const itemIds = [...new Set(ids.map(Number).filter(Number.isFinite))];
    if (!itemIds.length) return;
    try {
        const result = await requestBinAction("/api/bin/restore", { item_ids: itemIds });
        selectedItemIds.clear();
        showStashNotification(`Restored ${result.restored_count} ${result.restored_count === 1 ? "copy" : "copies"} to your Library.`);
        await loadClipboard();
    } catch (error) {
        alert(`Could not restore copies: ${error.message}`);
    }
}


async function saveBinSchedule(emptyAt) {
    try {
        const result = await requestBinAction("/api/bin/schedule", { empty_at: emptyAt });
        binSettings = result.settings;
        updateBinControls();
        showStashNotification(emptyAt ? "The Bin review reminder is scheduled. Nothing will be deleted automatically." : "The Bin review reminder was canceled. Your copies remain in the Bin.");
    } catch (error) {
        alert(`Could not update the Bin date: ${error.message}`);
    }
}


/* =========================================================
   LOAD MORE
========================================================= */

loadMoreButton?.addEventListener(
    "click",
    () => {

        visibleLimit += PAGE_SIZE;

        renderItems();

    }
);


/* =========================================================
   SORT
========================================================= */

document
    .getElementById("sortButton")
    ?.addEventListener(
        "click",
        () => {

            sortNewestFirst =
                !sortNewestFirst;

            document.getElementById(
                "sortButton"
            ).textContent =
                sortNewestFirst
                    ? "Newest first"
                    : "Oldest first";

            renderItems();

        }
    );


/* =========================================================
   REFRESH
========================================================= */

document
    .getElementById("refreshButton")
    ?.addEventListener(
        "click",
        loadClipboard
    );


/* =========================================================
   SIDEBAR COLLAPSE
========================================================= */

document
    .getElementById("collapseSidebar")
    ?.addEventListener(
        "click",
        () => {

            app.classList.toggle(
                "sidebar-collapsed"
            );

            localStorage.setItem(
                "copyMakerSidebarCollapsed",
                app.classList.contains(
                    "sidebar-collapsed"
                )
                    ? "1"
                    : "0"
            );

        }
    );


if (
    localStorage.getItem(
        "copyMakerSidebarCollapsed"
    ) === "1"
) {

    app.classList.add(
        "sidebar-collapsed"
    );

}


/* =========================================================
   SIDEBAR RESIZE
========================================================= */

const sidebarResizer =
    document.getElementById(
        "sidebarResizer"
    );

let resizingSidebar = false;


function startSidebarResize(event) {

    if (
        window.innerWidth <= 650
    )
        return;

    resizingSidebar = true;

    document.body.style.cursor =
        "col-resize";

    document.body.style.userSelect =
        "none";

    event.preventDefault();

}


function moveSidebarResize(event) {

    if (!resizingSidebar)
        return;

    const min =
        210;

    const max =
        420;

    const width =
        Math.min(
            max,
            Math.max(
                min,
                event.clientX
            )
        );

    app.style.setProperty(
        "--current-sidebar-width",
        `${width}px`
    );

    localStorage.setItem(
        "copyMakerSidebarWidth",
        String(width)
    );

}


function stopSidebarResize() {

    if (!resizingSidebar)
        return;

    resizingSidebar = false;

    document.body.style.cursor =
        "";

    document.body.style.userSelect =
        "";

}


sidebarResizer?.addEventListener(
    "pointerdown",
    startSidebarResize
);

window.addEventListener(
    "pointermove",
    moveSidebarResize
);

window.addEventListener(
    "pointerup",
    stopSidebarResize
);


const savedSidebarWidth =
    Number(
        localStorage.getItem(
            "copyMakerSidebarWidth"
        )
    );

if (
    Number.isFinite(savedSidebarWidth) &&
    savedSidebarWidth >= 210 &&
    savedSidebarWidth <= 420
) {

    app.style.setProperty(
        "--current-sidebar-width",
        `${savedSidebarWidth}px`
    );

}


/* =========================================================
   COPY VIEWER
========================================================= */

function getOpenTargets(item) {
    const type = getItemType(item);
    const name = String(item?.original_name || item?.filename || item?.name || "").toLowerCase();
    const mime = String(item?.mime_type || item?.mime || "").toLowerCase();
    const extension = name.includes(".") ? name.slice(name.lastIndexOf(".")) : "";
    const text = String(item?.text || item?.content || item?.value || "");
    const rawType = String(item?.type || item?.media_type || item?.kind || "").toLowerCase();
    const codeExtensions = new Set([
        ".py", ".pyw", ".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".css", ".scss",
        ".less", ".json", ".jsonl", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg",
        ".conf", ".c", ".h", ".cc", ".cpp", ".hpp", ".java", ".kt", ".swift", ".go",
        ".rs", ".rb", ".php", ".sh", ".zsh", ".bash", ".sql", ".vue", ".svelte",
        ".ipynb", ".makefile", ".dockerfile",
    ]);
    const developerTags = [rawType, item?.workspace_mode, item?.workspaceMode, item?.category, item?.subtype, item?.language]
        .filter(value => typeof value === "string").join(" ").toLowerCase();
    const isCode = codeExtensions.has(extension)
        || /\b(code|developer|source|snippet|script|config)\b/.test(developerTags)
        || /^(text\/(x-python|x-c|x-c\+\+|javascript|typescript|x-shellscript|x-sql)|application\/(json|javascript|xml|yaml|x-sh|x-python))/.test(mime)
        || /^#!.*\n/.test(text)
        || (text.includes("```"));

    if (type === "video" || mime.startsWith("video/") || [".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".mpeg", ".mpg"].includes(extension)) {
        return [["capcut", "CapCut"], ["davinci", "DaVinci Resolve"]];
    }
    if (isCode) return [["cursor", "Cursor"]];
    if (/\b(link|url|website)\b/.test(rawType) || /^https?:\/\//i.test(text.trim())) return [["default", "Default app"]];
    if (/\b(text|note|markdown)\b/.test(rawType) || [".txt", ".md", ".markdown", ".rtf", ".note"].includes(extension) || mime.startsWith("text/")) {
        return [["notes", "Notes"]];
    }
    if (type === "image" || mime.startsWith("image/") || [".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".tif", ".tiff", ".bmp"].includes(extension)) return [["preview", "Preview"]];
    return [["default", "Default app"]];
}

function addAppHandoff(item) {
    if (!item?.id) return;

    const handoff = document.createElement("section");
    handoff.className = "viewer-handoff";

    const heading = document.createElement("h3");
    heading.textContent = "Open a copy in";

    const description = document.createElement("p");
    description.textContent = "Stash keeps your saved original. A separate temporary copy will be prepared for the app you choose.";

    const buttons = document.createElement("div");
    buttons.className = "viewer-handoff-buttons";
    const status = document.createElement("p");
    status.className = "viewer-handoff-status";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");

    const supportedApps = getOpenTargets(item);

    for (const [app, label] of supportedApps) {
        const button = document.createElement("button");
        button.className = "viewer-handoff-button";
        button.type = "button";
        button.textContent = `Open in ${label}`;
        button.addEventListener("click", async () => {
            button.disabled = true;
            status.dataset.kind = "";
            status.textContent = `Preparing a copy and opening ${label}…`;
            try {
                const response = await fetch("/api/integrations/open-library-item", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ itemId: item.id, app }),
                });
                const result = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(result.error || "This file could not be sent to the app.");

                status.dataset.kind = result.appOpened ? "success" : "warning";
                status.textContent = result.appOpened
                    ? `${result.label} is open. ${result.nextStep}`
                    : `The copy is ready in Finder. ${result.label} did not open automatically. ${result.nextStep}`;
            } catch (error) {
                status.dataset.kind = "error";
                status.textContent = error.message || "This file could not be sent to the app.";
            } finally {
                button.disabled = false;
            }
        });
        buttons.append(button);
    }

    handoff.append(heading, description, buttons, status);
    viewerContent.append(handoff);
}

function openViewer(item) {

    if (!copyViewer)
        return;

    const type =
        getItemType(item);

    viewerTitle.textContent =
        item.original_name ||
        item.filename ||
        (
            type === "text"
                ? "Text copy"
                : `${type} copy`
        );


    viewerContent.innerHTML = "";


    if (type === "text") {

        const text =
            item.text ||
            item.content ||
            item.value ||
            "";

        const element =
            document.createElement(
                "div"
            );

        element.className =
            "viewer-text";

        element.textContent =
            text;

        viewerContent.appendChild(
            element
        );

        if (!item.trashed_at && item.id != null) {
            const vaultActions = document.createElement("div");
            vaultActions.className = "vault-library-move-actions";
            const moveButton = document.createElement("button");
            moveButton.className = "settings-secondary-button";
            moveButton.type = "button";
            moveButton.textContent = "Move this copy to Vault";
            const moveStatus = document.createElement("p");
            moveStatus.className = "settings-status";
            moveStatus.setAttribute("role", "status");
            moveStatus.setAttribute("aria-live", "polite");
            moveButton.addEventListener("click", async () => {
                moveButton.disabled = true;
                moveStatus.textContent = "Encrypting this copy in the Vault…";
                delete moveStatus.dataset.kind;
                try {
                    const response = await fetch("/api/vault/move-library-copy", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ item_id: item.id }),
                    });
                    const result = await response.json().catch(() => ({}));
                    if (!response.ok) throw new Error(result.error || "Stash could not move this copy to the Vault.");
                    closeViewer();
                    loadClipboard();
                    document.getElementById("vaultNavigation")?.click();
                } catch (error) {
                    moveStatus.textContent = error.message || "Stash could not move this copy to the Vault.";
                    moveStatus.dataset.kind = "error";
                    moveButton.disabled = false;
                }
            });
            vaultActions.append(moveButton, moveStatus);
            viewerContent.appendChild(vaultActions);
        }

    } else if (
        type === "image"
    ) {

        const image =
            document.createElement(
                "img"
            );

        image.className =
            "viewer-media";

        image.src =
            mediaUrl(item);

        image.alt =
            item.original_name ||
            "Copied image";

        viewerContent.appendChild(
            image
        );

    } else if (
        type === "audio"
    ) {

        const audio =
            document.createElement(
                "audio"
            );

        audio.className =
            "viewer-media";

        audio.controls = true;
        audio.src =
            mediaUrl(item);

        viewerContent.appendChild(
            audio
        );

    } else if (
        type === "video"
    ) {

        const video =
            document.createElement(
                "video"
            );

        video.className =
            "viewer-media";

        video.controls = true;
        video.preload = "metadata";
        video.src =
            mediaUrl(item);

        viewerContent.appendChild(
            video
        );

        const sharingActions = document.createElement("div");
        sharingActions.className = "viewer-video-sharing";

        const copyForSharing = document.createElement("button");
        copyForSharing.className = "viewer-share-video-button";
        copyForSharing.type = "button";
        copyForSharing.textContent = "Copy MP4 for sharing";

        const sharingStatus = document.createElement("p");
        sharingStatus.className = "viewer-share-video-status";
        sharingStatus.setAttribute("role", "status");
        sharingStatus.setAttribute("aria-live", "polite");

        copyForSharing.addEventListener("click", async () => {
            copyForSharing.disabled = true;
            sharingStatus.textContent = "Preparing a shareable MP4…";
            sharingStatus.dataset.kind = "";

            try {
                const response = await fetch(
                    `/api/videos/${encodeURIComponent(item.id)}/copy-to-clipboard`,
                    { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }
                );
                const result = await response.json().catch(() => ({}));
                if (!response.ok) {
                    throw new Error(result.error || "Stash could not prepare this video for sharing.");
                }

                if (result.item) {
                    Object.assign(item, result.item);
                }
                sharingStatus.dataset.kind = "success";
                sharingStatus.textContent = "MP4 copied. Go to WhatsApp or another app and paste it.";
            } catch (error) {
                sharingStatus.dataset.kind = "error";
                sharingStatus.textContent = error.message || "Stash could not copy this video.";
            } finally {
                copyForSharing.disabled = false;
            }
        });

        sharingActions.append(copyForSharing, sharingStatus);
        viewerContent.appendChild(sharingActions);

    } else {

        const file =
            document.createElement(
                "div"
            );

        file.className =
            "viewer-file";

        file.innerHTML = `
            <strong>
                ${escapeHtml(
                    item.original_name ||
                    item.filename ||
                    item.name ||
                    "File"
                )}
            </strong>

            <br><br>

            ${escapeHtml(
                formatSize(
                    item.size ||
                    item.file_size
                )
            )}
        `;

        viewerContent.appendChild(
            file
        );

    }

    addAppHandoff(item);


    copyViewer.hidden = false;
    copyViewer.setAttribute(
        "aria-hidden",
        "false"
    );

}


function closeViewer() {

    if (!copyViewer)
        return;

    copyViewer.hidden = true;

    copyViewer.setAttribute(
        "aria-hidden",
        "true"
    );

    viewerContent.innerHTML = "";

}


document.addEventListener(
    "click",
    event => {

        if (
            event.target.closest(
                "[data-close-viewer]"
            )
        ) {

            closeViewer();
            return;

        }

        if (
            event.target.closest(
                "#closeViewer"
            )
        ) {

            closeViewer();
            return;

        }

        const restoreButton = event.target.closest("[data-bin-restore]");
        if (restoreButton) {
            event.preventDefault();
            event.stopPropagation();
            restoreBinItems([Number(restoreButton.dataset.binRestore)]);
            return;
        }

        if (event.target.closest("[data-copy-select], .copy-select-wrap")) return;


        const row =
            event.target.closest(
                ".copy-row"
            );

        if (!row)
            return;

        const item =
            row._copyMakerItem;

        if (item?.capture_status && item.capture_status !== "ready")
            return;

        if (item)
            openViewer(item);

    }
);


/* =========================================================
   BIN NOTIFICATIONS
   Shared endpoint retained for Bin reminders.
========================================================= */

async function checkStashNotifications() {

    try {

        const response =
            await fetch(
                "/api/notifications"
            );


        if (!response.ok)
            return;


        const notifications =
            await response.json();


        notifications.forEach(
            notification => {

                showStashNotification(
                    notification.message
                );

            }
        );


        if (
            notifications.length
        ) {

            loadClipboard();

        }


    } catch {
        // Notification polling is optional; keep the app usable when it is unavailable.

    }

}


function showStashNotification(
    message
) {

    const toast =
        document.createElement(
            "div"
        );


    toast.className =
        "stash-notification-toast";


    toast.innerHTML = `

        <div class="stash-notification-toast-title">
            Stash
        </div>

        <div>
            ${escapeHtml(message)}
        </div>

    `;


    document.body.appendChild(
        toast
    );


    setTimeout(
        () => {
            toast.classList.add(
                "show"
            );
        },
        10
    );


    setTimeout(
        () => {

            toast.classList.remove(
                "show"
            );


            setTimeout(
                () => {

                    toast.remove();

                },
                300
            );

        },
        5000
    );

}


/* =========================================================
   NEW COPY
========================================================= */

document
    .getElementById("newCopyButton")
    ?.addEventListener(
        "click",
        () => {
            document.dispatchEvent(new CustomEvent("copy-maker:new-chat"));
        }
    );


/* =========================================================
   INITIALIZE
========================================================= */

let copyMakerInitialized = false;

function startAuthenticatedWorkspace(username) {
    if (copyMakerInitialized) return;
    copyMakerInitialized = true;

    const authScreen = document.getElementById("authScreen");
    const profileButton = document.getElementById("logoutButton") || document.getElementById("settingsSignOut");
    if (authScreen) authScreen.hidden = true;
    if (app) app.hidden = false;
    if (profileButton && username) {
        if (profileButton.id === "logoutButton") {
            profileButton.textContent = username.slice(0, 1).toUpperCase();
        }
        profileButton.dataset.username = username;
        profileButton.title = `Signed in as ${username}.`;
        profileButton.setAttribute("aria-label", `Sign out ${username}`);
    }

    loadClipboard();
    document.dispatchEvent(new CustomEvent("copy-maker:workspace-ready"));
    window.setInterval(loadClipboard, 1000);
    window.setInterval(checkStashNotifications, 2000);
}

function setAuthenticationMode(status) {
    const title = document.getElementById("authTitle");
    const subtitle = document.getElementById("authSubtitle");
    const username = document.getElementById("authUsername");
    const password = document.getElementById("authPassword");
    const confirmField = document.getElementById("authConfirmField");
    const confirmation = document.getElementById("authPasswordConfirm");
    const submit = document.getElementById("authSubmit");
    const twoFactorForm = document.getElementById("twoFactorLoginForm");
    const authForm = document.getElementById("authForm");

    const creating = !status.configured && status.can_create_account;
    const remoteBeforeSetup = !status.configured && !status.can_create_account;

    if (title) title.textContent = creating ? "Create your local library" : "Welcome back";
    if (subtitle) {
        subtitle.textContent = remoteBeforeSetup
            ? "Create the first account on this Mac before signing in here."
            : creating
                ? "Save a copy here, then find it again when you need it. Your library stays on this Mac."
                : "Sign in to open your Stash workspace.";
    }

    if (confirmField) confirmField.hidden = !creating;
    if (twoFactorForm) twoFactorForm.hidden = true;
    if (authForm) authForm.hidden = false;
    if (confirmation) {
        confirmation.disabled = !creating;
        confirmation.required = creating;
    }
    if (password) password.autocomplete = creating ? "new-password" : "current-password";
    if (submit) {
        submit.textContent = creating ? "Create account" : "Sign in";
        submit.disabled = remoteBeforeSetup;
    }
    if (username) username.focus();
}

function showTwoFactorLoginChallenge() {
    const authForm = document.getElementById("authForm");
    const challengeForm = document.getElementById("twoFactorLoginForm");
    const title = document.getElementById("authTitle");
    const subtitle = document.getElementById("authSubtitle");
    const authMessage = document.getElementById("authMessage");
    if (authForm) authForm.hidden = true;
    if (challengeForm) challengeForm.hidden = false;
    if (title) title.textContent = "Verify it’s you";
    if (subtitle) subtitle.textContent = "Enter a six-digit authenticator code, or one of your saved recovery codes.";
    if (authMessage) authMessage.textContent = "";
    document.getElementById("twoFactorLoginCode")?.focus();
}

async function initializeAuthentication() {
    const authForm = document.getElementById("authForm");
    const authMessage = document.getElementById("authMessage");
    const authSubmit = document.getElementById("authSubmit");
    const authPassword = document.getElementById("authPassword");
    const authConfirmation = document.getElementById("authPasswordConfirm");
    const logoutButton = document.getElementById("logoutButton") || document.getElementById("settingsSignOut");
    const twoFactorLoginForm = document.getElementById("twoFactorLoginForm");
    const twoFactorLoginCode = document.getElementById("twoFactorLoginCode");
    const twoFactorLoginSubmit = document.getElementById("twoFactorLoginSubmit");
    const cancelTwoFactorLogin = document.getElementById("cancelTwoFactorLogin");

    let authStatus;
    try {
        const response = await fetch("/api/auth/status", { cache: "no-store" });
        if (!response.ok) throw new Error("Could not check the account status.");
        authStatus = await response.json();
    } catch (error) {
        if (authMessage) authMessage.textContent = "Stash could not connect. Refresh this page and try again.";
        if (authSubmit) authSubmit.disabled = true;
        return;
    }

    if (authStatus.authenticated) {
        startAuthenticatedWorkspace(authStatus.username || "Stash");
    } else if (authStatus.two_factor_challenge_pending) {
        showTwoFactorLoginChallenge();
    } else {
        setAuthenticationMode(authStatus);
    }

    authForm?.addEventListener("submit", async event => {
        event.preventDefault();
        if (!authStatus.configured && !authStatus.can_create_account) return;

        const creating = !authStatus.configured;
        const username = document.getElementById("authUsername")?.value.trim() || "";
        const password = authPassword?.value || "";
        if (creating && password !== (authConfirmation?.value || "")) {
            if (authMessage) authMessage.textContent = "The passwords do not match.";
            authConfirmation?.focus();
            return;
        }

        if (authSubmit) {
            authSubmit.disabled = true;
            authSubmit.textContent = creating ? "Creating account…" : "Signing in…";
        }
        if (authMessage) authMessage.textContent = "";

        try {
            const response = await fetch(creating ? "/api/auth/signup" : "/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password })
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || "Sign-in failed. Please try again.");
            if (result.requires_two_factor) {
                showTwoFactorLoginChallenge();
                return;
            }
            authStatus = { ...authStatus, configured: true, authenticated: true };
            startAuthenticatedWorkspace(result.username || username);
        } catch (error) {
            if (authMessage) authMessage.textContent = error.message;
            if (authSubmit) {
                authSubmit.disabled = false;
                authSubmit.textContent = creating ? "Create account" : "Sign in";
            }
        }
    });

    twoFactorLoginForm?.addEventListener("submit", async event => {
        event.preventDefault();
        if (twoFactorLoginSubmit) {
            twoFactorLoginSubmit.disabled = true;
            twoFactorLoginSubmit.textContent = "Checking code…";
        }
        if (authMessage) authMessage.textContent = "";
        try {
            const response = await fetch("/api/auth/two-factor/verify", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ code: twoFactorLoginCode?.value || "" }),
                cache: "no-store",
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || "That code could not be verified.");
            startAuthenticatedWorkspace(result.username || "Stash");
        } catch (error) {
            if (authMessage) authMessage.textContent = error.message;
        } finally {
            if (twoFactorLoginSubmit) {
                twoFactorLoginSubmit.disabled = false;
                twoFactorLoginSubmit.textContent = "Verify and sign in";
            }
        }
    });

    cancelTwoFactorLogin?.addEventListener("click", async () => {
        await fetch("/api/auth/two-factor/cancel", { method: "POST" }).catch(() => {});
        window.location.reload();
    });

    logoutButton?.addEventListener("click", async () => {
        logoutButton.disabled = true;
        try {
            await fetch("/api/auth/logout", { method: "POST" });
        } finally {
            document.dispatchEvent(new CustomEvent("copy-maker:sign-out"));
            window.location.reload();
        }
    });
}

initializeAuthentication();



/* =========================================================
   AVA AI ASSISTANT
========================================================= */

(() => {

    const avaToggle = document.getElementById("avaToggle");
    const avaPanel = document.getElementById("avaPanel");
    const avaClose = document.getElementById("avaClose");

    const avaForm = document.getElementById("avaForm");
    const avaInput = document.getElementById("avaInput");
    const avaVoiceButton = document.getElementById("avaVoiceButton");
    const avaVoiceStatus = document.getElementById("avaVoiceStatus");
    const avaMessages = document.getElementById("avaMessages");
    const avaLibraryVoiceButton = document.getElementById("avaLibraryVoiceButton");
    const avaPetMicButton = document.getElementById("avaPetMicButton");
    const chatEmptyState = document.getElementById("chatEmptyState");
    const conversationList = document.getElementById("conversationList");
    const avaTyping = document.getElementById("avaTyping");
    const avaStopButton = document.getElementById("avaStopButton");
    const avaSendButton = document.getElementById("avaSend");

    const avaConfirmation = document.getElementById("avaConfirmation");
    const avaConfirmYes = document.getElementById("avaConfirmYes");
    const avaConfirmNo = document.getElementById("avaConfirmNo");

    let pendingDeleteItem = null;
    let pendingDeleteConfirmationToken = null;
    let pendingConfirmationType = null;
    let pendingFileOrganizationToken = null;
    let pendingFileActionToken = null;
    let pendingOrganizeFilters = null;
    let pendingFileCopyCommand = null;
    let pendingMobileActionId = null;
    let mobileActionPollTimer = null;
    let activeVoiceRecognition = null;
    let activeRequestController = null;
    let voiceReplyMode = false;
    let avaInputMode = "text";

    function stopMobileActionPolling() {
        if (mobileActionPollTimer) clearTimeout(mobileActionPollTimer);
        mobileActionPollTimer = null;
        pendingMobileActionId = null;
    }

    function watchMobileActionDecision(actionId) {
        stopMobileActionPolling();
        if (!actionId || !pendingFileActionToken) return;
        pendingMobileActionId = actionId;
        const poll = async () => {
            if (pendingMobileActionId !== actionId) return;
            try {
                const response = await fetch(`/api/mobile-companion/action-status/${encodeURIComponent(actionId)}`, { cache: "no-store" });
                const result = await response.json().catch(() => ({}));
                if (!response.ok) {
                    stopMobileActionPolling();
                    return;
                }
                if (result.status === "approved") {
                    mobileActionPollTimer = setTimeout(poll, 500);
                    return;
                }
                if (result.status === "executing") {
                    if (avaConfirmYes) avaConfirmYes.disabled = true;
                    if (avaConfirmNo) avaConfirmNo.disabled = true;
                    const note = avaConfirmation.querySelector(".confirmation-note");
                    if (note) note.textContent = "Approved on your phone. Desktop Stash is carrying out the preview.";
                    mobileActionPollTimer = setTimeout(poll, 1000);
                    return;
                }
                if (result.status === "rejected") {
                    stopMobileActionPolling();
                    addAvaMessage("The preview was declined on your phone.");
                    avaConfirmNo?.click();
                    return;
                }
                if (result.status === "executed" || result.status === "error") {
                    stopMobileActionPolling();
                    addAvaMessage(result.message || (result.status === "executed"
                        ? "The action approved on your phone is complete."
                        : "Desktop Stash could not complete the action approved on your phone."));
                    avaConfirmation.hidden = true;
                    pendingDeleteItem = null;
                    pendingDeleteConfirmationToken = null;
                    pendingConfirmationType = null;
                    pendingOrganizeFilters = null;
                    pendingFileOrganizationToken = null;
                    pendingFileActionToken = null;
                    if (result.status === "executed") loadClipboard();
                    return;
                }
            } catch {
                // Keep the preview available if the Wi-Fi link briefly drops.
            }
            mobileActionPollTimer = setTimeout(poll, 1500);
        };
        mobileActionPollTimer = setTimeout(poll, 1500);
    }

    const conversationStorageKey = "copyMakerAvaConversationsV1";
    const activeConversationStorageKey = "copyMakerAvaActiveConversation";
    let avaConversations = [];
    let activeConversationId = localStorage.getItem(activeConversationStorageKey);

    try {
        const saved = JSON.parse(localStorage.getItem(conversationStorageKey) || "[]");
        if (Array.isArray(saved)) {
            avaConversations = saved.filter(item =>
                item && typeof item.id === "string" && Array.isArray(item.messages)
            ).slice(0, 40);
        }
    } catch (error) {
        avaConversations = [];
    }


    function saveAvaConversations() {
        try {
            avaConversations = avaConversations
                .sort((a, b) => b.updatedAt - a.updatedAt)
                .slice(0, 40);
            localStorage.setItem(conversationStorageKey, JSON.stringify(avaConversations));
            if (activeConversationId) {
                localStorage.setItem(activeConversationStorageKey, activeConversationId);
            } else {
                localStorage.removeItem(activeConversationStorageKey);
            }
        } catch (error) {
            console.warn("Could not save Ava chat history:", error);
        }
    }


    function conversationGroup(timestamp) {
        const days = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(timestamp).setHours(0, 0, 0, 0)) / 86400000);
        if (days <= 0) return "Today";
        if (days === 1) return "Yesterday";
        if (days <= 7) return "Previous 7 days";
        return "Older";
    }


    function renderConversationList() {
        if (!conversationList) return;
        conversationList.replaceChildren();
        const groups = ["Today", "Yesterday", "Previous 7 days", "Older"];
        const grouped = new Map(groups.map(group => [group, []]));
        avaConversations.forEach(conversation => {
            const group = conversationGroup(conversation.updatedAt || Date.now());
            grouped.get(group).push(conversation);
        });

        groups.forEach(group => {
            const entries = grouped.get(group);
            if (!entries.length) return;
            const heading = document.createElement("div");
            heading.className = "conversation-group-heading";
            heading.textContent = group;
            conversationList.appendChild(heading);

            entries.forEach(conversation => {
                const row = document.createElement("div");
                row.className = "conversation-row" + (conversation.id === activeConversationId ? " active" : "");
                row.dataset.conversationId = conversation.id;

                const select = document.createElement("button");
                select.type = "button";
                select.className = "conversation-select";
                select.textContent = conversation.title || "New chat";
                select.setAttribute("aria-label", `Open chat: ${conversation.title || "New chat"}`);
                select.addEventListener("click", () => openSavedConversation(conversation.id));

                const more = document.createElement("button");
                more.type = "button";
                more.className = "conversation-more";
                more.textContent = "···";
                more.setAttribute("aria-label", `More actions for ${conversation.title || "chat"}`);
                more.title = "Rename or delete chat";

                const menu = document.createElement("div");
                menu.className = "conversation-menu";
                menu.hidden = true;
                const rename = document.createElement("button");
                rename.type = "button";
                rename.textContent = "Rename";
                const remove = document.createElement("button");
                remove.type = "button";
                remove.textContent = "Delete";
                remove.className = "delete-action";
                more.addEventListener("click", event => {
                    event.stopPropagation();
                    document.querySelectorAll(".conversation-menu").forEach(other => {
                        if (other !== menu) other.hidden = true;
                    });
                    menu.hidden = !menu.hidden;
                });
                rename.addEventListener("click", event => {
                    event.stopPropagation();
                    const next = window.prompt("Rename this chat", conversation.title || "New chat");
                    if (next?.trim()) {
                        conversation.title = next.trim().slice(0, 80);
                        saveAvaConversations();
                        renderConversationList();
                    }
                });
                remove.addEventListener("click", event => {
                    event.stopPropagation();
                    if (!window.confirm(`Delete “${conversation.title || "New chat"}”?`)) return;
                    avaConversations = avaConversations.filter(item => item.id !== conversation.id);
                    if (activeConversationId === conversation.id) startNewAvaChat();
                    saveAvaConversations();
                    renderConversationList();
                });

                menu.append(rename, remove);
                row.append(select, more, menu);
                conversationList.appendChild(row);
            });
        });

        if (!avaConversations.length) {
            const note = document.createElement("p");
            note.className = "conversation-empty";
            note.textContent = "Your Ava chats will appear here.";
            conversationList.appendChild(note);
        }
    }


    function appendInlineMarkdown(parent, value) {
        const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g;
        let cursor = 0;
        let match;
        while ((match = pattern.exec(value))) {
            if (match.index > cursor) parent.appendChild(document.createTextNode(value.slice(cursor, match.index)));
            const token = match[0];
            let node;
            if (token.startsWith("**")) {
                node = document.createElement("strong");
                node.textContent = token.slice(2, -2);
            } else if (token.startsWith("*")) {
                node = document.createElement("em");
                node.textContent = token.slice(1, -1);
            } else if (token.startsWith("`")) {
                node = document.createElement("code");
                node.textContent = token.slice(1, -1);
            } else {
                const parts = token.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
                node = document.createElement("a");
                node.textContent = parts[1];
                node.href = parts[2];
                node.target = "_blank";
                node.rel = "noopener noreferrer";
            }
            parent.appendChild(node);
            cursor = pattern.lastIndex;
        }
        if (cursor < value.length) parent.appendChild(document.createTextNode(value.slice(cursor)));
    }


    function renderAvaMarkdown(container, raw) {
        container.replaceChildren();
        const lines = String(raw).split("\n");
        let index = 0;
        while (index < lines.length) {
            const line = lines[index];
            if (/^\s*```/.test(line)) {
                const language = line.replace(/^\s*```/, "").trim() || "code";
                const codeLines = [];
                index++;
                while (index < lines.length && !/^\s*```/.test(lines[index])) codeLines.push(lines[index++]);
                if (index < lines.length) index++;
                const block = document.createElement("div");
                block.className = "ava-code-block";
                const header = document.createElement("div");
                header.className = "ava-code-header";
                const label = document.createElement("span");
                label.textContent = language;
                const copy = document.createElement("button");
                copy.type = "button";
                copy.textContent = "Copy";
                copy.addEventListener("click", async () => {
                    try {
                        await navigator.clipboard.writeText(codeLines.join("\n"));
                        copy.textContent = "Copied";
                        window.setTimeout(() => { copy.textContent = "Copy"; }, 1200);
                    } catch (error) {
                        copy.textContent = "Unavailable";
                    }
                });
                header.append(label, copy);
                const pre = document.createElement("pre");
                const code = document.createElement("code");
                code.className = `language-${language.replace(/[^a-z0-9_-]/gi, "")}`;
                code.textContent = codeLines.join("\n");
                pre.appendChild(code);
                block.append(header, pre);
                container.appendChild(block);
                continue;
            }
            const heading = line.match(/^(#{1,3})\s+(.+)$/);
            if (heading) {
                const element = document.createElement(`h${heading[1].length}`);
                appendInlineMarkdown(element, heading[2]);
                container.appendChild(element);
                index++;
                continue;
            }
            if (/^\s*[-*]\s+/.test(line)) {
                const list = document.createElement("ul");
                while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
                    const item = document.createElement("li");
                    appendInlineMarkdown(item, lines[index++].replace(/^\s*[-*]\s+/, ""));
                    list.appendChild(item);
                }
                container.appendChild(list);
                continue;
            }
            if (/^\s*\d+\.\s+/.test(line)) {
                const list = document.createElement("ol");
                while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
                    const item = document.createElement("li");
                    appendInlineMarkdown(item, lines[index++].replace(/^\s*\d+\.\s+/, ""));
                    list.appendChild(item);
                }
                container.appendChild(list);
                continue;
            }
            if (!line.trim()) {
                index++;
                continue;
            }
            const paragraph = document.createElement("p");
            while (index < lines.length && lines[index].trim() && !/^\s*```/.test(lines[index]) && !/^#{1,3}\s+/.test(lines[index]) && !/^\s*[-*]\s+/.test(lines[index]) && !/^\s*\d+\.\s+/.test(lines[index])) {
                if (paragraph.childNodes.length) paragraph.appendChild(document.createElement("br"));
                appendInlineMarkdown(paragraph, lines[index++]);
            }
            container.appendChild(paragraph);
        }
    }


    function appendAvaContent(element, forceScroll = false) {
        const wasNearBottom = avaMessages.scrollHeight - avaMessages.scrollTop - avaMessages.clientHeight < 80;
        avaMessages.appendChild(element);
        avaMessages.hidden = false;
        chatEmptyState.hidden = true;
        const scrollButton = document.getElementById("avaScrollBottom");
        if (forceScroll || wasNearBottom) {
            avaMessages.scrollTop = avaMessages.scrollHeight;
            if (scrollButton) scrollButton.hidden = true;
        } else if (scrollButton) {
            scrollButton.hidden = false;
        }
    }


    function appendStoredMessage(message) {
        const type = message.role === "user" ? "user" : "ai";
        const div = document.createElement("div");
        div.className = type === "user" ? "ava-message ava-message-user" : "ava-message ava-message-ai";
        if (type === "ai") {
            const avatar = document.createElement("span");
            avatar.className = "ava-message-avatar";
            avatar.setAttribute("aria-hidden", "true");
            avatar.textContent = "A";
            div.appendChild(avatar);
        }
        const text = document.createElement("span");
        text.className = "ava-message-text";
        if (type === "ai") renderAvaMarkdown(text, message.text);
        else text.textContent = message.text;
        div.appendChild(text);
        if (type === "ai" && "speechSynthesis" in window && typeof SpeechSynthesisUtterance !== "undefined") {
            const speakButton = document.createElement("button");
            speakButton.type = "button";
            speakButton.className = "ava-speak-button";
            speakButton.textContent = "🔊";
            speakButton.setAttribute("aria-label", "Read Ava’s reply aloud");
            speakButton.addEventListener("click", () => speakAvaMessage(message.text));
            div.appendChild(speakButton);
        }
        avaMessages.appendChild(div);
    }


    function openSavedConversation(id) {
        const conversation = avaConversations.find(item => item.id === id);
        if (!conversation) return;
        if (activeRequestController) {
            const pending = activeRequestController;
            activeRequestController = null;
            pending.abort();
        }
        avaInput.disabled = false;
        avaVoiceButton.disabled = false;
        avaStopButton.hidden = true;
        avaTyping.hidden = true;
        activeConversationId = id;
        saveAvaConversations();
        renderConversationList();
        avaMessages.replaceChildren();
        conversation.messages.forEach(appendStoredMessage);
        avaMessages.hidden = conversation.messages.length === 0;
        chatEmptyState.hidden = conversation.messages.length > 0;
        avaConfirmation.hidden = true;
        document.getElementById("avaScrollBottom").hidden = true;
        pendingDeleteItem = null;
        pendingDeleteConfirmationToken = null;
        pendingConfirmationType = null;
        pendingFileOrganizationToken = null;
        pendingFileActionToken = null;
        pendingOrganizeFilters = null;
        pendingFileCopyCommand = null;
        showChatWorkspace();
        avaMessages.scrollTop = avaMessages.scrollHeight;
        avaSendButton.disabled = !avaInput.value.trim();
        avaInput.focus();
    }


    function startNewAvaChat() {
        if (activeRequestController) {
            const pending = activeRequestController;
            activeRequestController = null;
            pending.abort();
        }
        avaInput.disabled = false;
        avaVoiceButton.disabled = false;
        avaStopButton.hidden = true;
        avaTyping.hidden = true;
        avaSendButton.disabled = true;
        activeConversationId = null;
        saveAvaConversations();
        avaMessages.replaceChildren();
        avaMessages.hidden = true;
        chatEmptyState.hidden = false;
        avaConfirmation.hidden = true;
        avaTyping.hidden = true;
        document.getElementById("avaScrollBottom").hidden = true;
        pendingDeleteItem = null;
        pendingDeleteConfirmationToken = null;
        pendingConfirmationType = null;
        pendingFileOrganizationToken = null;
        pendingFileActionToken = null;
        pendingOrganizeFilters = null;
        pendingFileCopyCommand = null;
        avaInput.value = "";
        avaInput.style.height = "auto";
        showChatWorkspace();
        renderConversationList();
        avaInput.focus();
    }


    function rememberAvaMessage(message, type) {
        let conversation = avaConversations.find(item => item.id === activeConversationId);
        if (!conversation) {
            const firstUserMessage = type === "user" ? message : "New chat";
            conversation = {
                id: (window.crypto?.randomUUID && window.crypto.randomUUID()) || `chat-${Date.now()}`,
                title: firstUserMessage.trim().replace(/\s+/g, " ").slice(0, 42) || "New chat",
                messages: [],
                createdAt: Date.now(),
                updatedAt: Date.now()
            };
            activeConversationId = conversation.id;
            avaConversations.unshift(conversation);
        }
        conversation.messages.push({ role: type === "user" ? "user" : "assistant", text: message });
        conversation.updatedAt = Date.now();
        saveAvaConversations();
        renderConversationList();
    }


    renderConversationList();
    const savedActiveConversation = avaConversations.find(item => item.id === activeConversationId);
    if (savedActiveConversation) openSavedConversation(savedActiveConversation.id);


    document.addEventListener("copy-maker:new-chat", startNewAvaChat);
    conversationList?.addEventListener("click", event => {
        if (!event.target.closest(".conversation-menu")) {
            document.querySelectorAll(".conversation-menu").forEach(menu => { menu.hidden = true; });
        }
    });


    function speakAvaMessage(message) {

        if (
            !("speechSynthesis" in window) ||
            typeof SpeechSynthesisUtterance === "undefined"
        ) {
            return;
        }

        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(message);
        utterance.lang = navigator.language || "en-US";
        let voiceStyle = "cartoon";
        try {
            voiceStyle = localStorage.getItem("stashAvaVoiceStyleV1") || voiceStyle;
        } catch {
            // Keep the default voice style if preferences are unavailable.
        }
        if (voiceStyle === "off") return;
        if (voiceStyle === "cartoon") {
            utterance.pitch = 1.45;
            utterance.rate = 1.06;
        }
        window.speechSynthesis.speak(utterance);
    }


    function addAvaMessage(message, type = "ai") {

        const div = document.createElement("div");

        div.className =
            type === "user"
                ? "ava-message ava-message-user"
                : "ava-message ava-message-ai";

        if (type !== "user") {
            const avatar = document.createElement("span");
            avatar.className = "ava-message-avatar";
            avatar.setAttribute("aria-hidden", "true");
            avatar.textContent = "A";
            div.appendChild(avatar);
        }

        const text = document.createElement("span");
        text.className = "ava-message-text";
        renderAvaMarkdown(text, message);
        div.appendChild(text);

        if (
            type !== "user" &&
            "speechSynthesis" in window &&
            typeof SpeechSynthesisUtterance !== "undefined"
        ) {
            const speakButton = document.createElement("button");
            speakButton.type = "button";
            speakButton.className = "ava-speak-button";
            speakButton.textContent = "🔊";
            speakButton.setAttribute("aria-label", "Read Ava’s reply aloud");
            speakButton.title = "Read aloud";
            speakButton.addEventListener("click", () => speakAvaMessage(message));
            div.appendChild(speakButton);
        }

        appendAvaContent(div, type === "user");
        rememberAvaMessage(message, type);
    }


    function beginAvaVoiceInput({ autoSubmit = false } = {}) {

        if (activeVoiceRecognition) {
            avaVoiceStatus.textContent = "Stopping voice input…";
            voiceReplyMode = false;
            activeVoiceRecognition.stop();
            return;
        }

        const Recognition =
            window.SpeechRecognition || window.webkitSpeechRecognition;

        if (!Recognition) {
            avaVoiceStatus.textContent =
                "Voice input isn’t supported in this browser. You can still type to Ava.";
            voiceReplyMode = false;
            window.dispatchEvent(new CustomEvent("stash:ava-voice-error", {
                detail: { message: "This browser can’t listen yet. You can still type to me." }
            }));
            return;
        }

        const recognition = new Recognition();
        const startingText = avaInput.value.trim();
        let voiceError = "";
        let voiceErrorType = "";
        let capturedTranscript = "";

        recognition.lang = navigator.language || "en-US";
        recognition.continuous = false;
        recognition.interimResults = true;
        activeVoiceRecognition = recognition;

        avaVoiceButton.classList.add("is-listening");
        avaLibraryVoiceButton?.classList.add("is-listening");
        avaPetMicButton?.classList.add("is-listening");
        avaLibraryVoiceButton?.setAttribute("aria-label", "Listening to Ava; stop voice input");
        avaLibraryVoiceButton?.setAttribute("title", "Stop listening");
        avaPetMicButton?.setAttribute("aria-label", "Stop talking to Ava");
        avaPetMicButton?.setAttribute("title", "Stop listening");
        avaVoiceButton.textContent = "■";
        avaVoiceButton.setAttribute("aria-label", "Stop voice input");
        avaVoiceButton.title = "Stop listening";
        avaVoiceStatus.textContent = "Listening… Click the microphone again to stop.";

        recognition.onresult = (event) => {
            const transcript = Array.from(event.results)
                .map(result => result[0]?.transcript || "")
                .join(" ")
                .trim();

            avaInput.value = [startingText, transcript]
                .filter(Boolean)
                .join(" ");
            capturedTranscript = transcript;
            if (transcript) avaInputMode = "voice";
            avaInput.dispatchEvent(new Event("input", { bubbles: true }));
        };

        recognition.onerror = (event) => {
            voiceErrorType = event.error || "";
            if (event.error === "not-allowed" || event.error === "service-not-allowed") {
                voiceError = "Microphone access is blocked. Allow it in browser settings, or keep typing.";
            } else if (event.error === "no-speech") {
                voiceError = "I didn’t hear speech. Try again or type your request.";
            } else {
                voiceError = "Voice input couldn’t start. You can still type to Ava.";
            }
        };

        recognition.onend = () => {
            activeVoiceRecognition = null;
            avaVoiceButton.classList.remove("is-listening");
            avaLibraryVoiceButton?.classList.remove("is-listening");
            avaPetMicButton?.classList.remove("is-listening");
            avaLibraryVoiceButton?.setAttribute("aria-label", "Ask Ava by voice");
            avaLibraryVoiceButton?.setAttribute("title", "Ask Ava by voice");
            avaPetMicButton?.setAttribute("aria-label", "Talk to Ava");
            avaPetMicButton?.setAttribute("title", "Talk to Ava");
            avaVoiceButton.textContent = "🎙";
            avaVoiceButton.setAttribute("aria-label", "Start voice input");
            avaVoiceButton.title = "Speak to Ava";

            if (voiceError) {
                avaVoiceStatus.textContent = voiceError;
                voiceReplyMode = false;
                window.dispatchEvent(new CustomEvent("stash:ava-voice-error", {
                    detail: { message: voiceErrorType === "no-speech" ? "I didn’t catch that. Try me again?" : "I can’t hear you yet. Check microphone permission and try again." }
                }));
            } else if (avaInput.value.trim() !== startingText) {
                if (autoSubmit && capturedTranscript) {
                    avaVoiceStatus.textContent = "I heard you. One moment…";
                    window.setTimeout(() => askAva(capturedTranscript, "voice"), 0);
                } else {
                    avaVoiceStatus.textContent = "Voice text added. Review it, then press Send.";
                    avaInput.focus();
                }
            } else {
                avaVoiceStatus.textContent = "No speech captured. You can try again or type.";
                voiceReplyMode = false;
                window.dispatchEvent(new CustomEvent("stash:ava-voice-error", {
                    detail: { message: "I didn’t catch anything. Try me again?" }
                }));
            }
        };

        try {
            recognition.start();
        } catch (error) {
            activeVoiceRecognition = null;
            avaVoiceButton.classList.remove("is-listening");
            avaLibraryVoiceButton?.classList.remove("is-listening");
            avaPetMicButton?.classList.remove("is-listening");
            avaLibraryVoiceButton?.setAttribute("aria-label", "Ask Ava by voice");
            avaLibraryVoiceButton?.setAttribute("title", "Ask Ava by voice");
            avaPetMicButton?.setAttribute("aria-label", "Talk to Ava");
            avaPetMicButton?.setAttribute("title", "Talk to Ava");
            avaVoiceButton.textContent = "🎙";
            avaVoiceButton.setAttribute("aria-label", "Start voice input");
            avaVoiceButton.title = "Speak to Ava";
            avaVoiceStatus.textContent = "Voice input couldn’t start. You can still type to Ava.";
            voiceReplyMode = false;
            window.dispatchEvent(new CustomEvent("stash:ava-voice-error", {
                detail: { message: "I couldn’t start listening. Check the browser’s microphone permission." }
            }));
        }
    }


    function requestAvaVoiceInput() {
        openAva();
        avaInput.value = "";
        avaInput.dispatchEvent(new Event("input", { bubbles: true }));
        voiceReplyMode = true;
        window.dispatchEvent(new CustomEvent("stash:ava-voice-listening"));
        beginAvaVoiceInput({ autoSubmit: true });
    }


    function getAvaItemLabel(item) {

        const label = [
            item.title,
            item.original_name,
            item.name,
            item.content,
            item.page_url,
            item.url
        ].find(value => typeof value === "string" && value.trim());

        if (label) {
            const trimmedLabel = label.trim();
            return trimmedLabel.length > 180
                ? `${trimmedLabel.slice(0, 177)}...`
                : trimmedLabel;
        }

        return item.type
            ? `${item.type} #${item.id || "saved item"}`
            : `Saved item #${item.id || ""}`;
    }


    function getAvaItemUrl(item) {

        const candidates = [item.open_url, item.page_url, item.url, item.source_url];

        for (const candidate of candidates) {

            if (typeof candidate !== "string" || !candidate.trim()) {
                continue;
            }

            const markdownLink = candidate.match(/\]\((https?:\/\/[^)]+)\)/);
            const rawUrl = markdownLink ? markdownLink[1] : candidate.trim();

            try {

                const parsedUrl = new URL(rawUrl, window.location.origin);
                const isWebUrl =
                    parsedUrl.protocol === "http:" ||
                    parsedUrl.protocol === "https:";
                const isLocalPath =
                    rawUrl.startsWith("/") &&
                    parsedUrl.origin === window.location.origin;

                if (isWebUrl || isLocalPath) {
                    return parsedUrl.href;
                }

            } catch (error) {
                continue;
            }
        }

        return null;
    }


    function addAvaResults(items, heading = "Saved items") {

        const validItems = items.filter(
            item => item && typeof item === "object"
        );

        if (!validItems.length) {
            return;
        }

        const message = document.createElement("div");
        message.className = "ava-message ava-message-ai ava-result-message";

        const title = document.createElement("div");
        title.className = "ava-result-heading";
        title.textContent = heading;
        message.appendChild(title);

        const list = document.createElement("div");
        list.className = "ava-result-list";

        validItems.slice(0, 8).forEach(item => {

            const row = document.createElement("div");
            row.className = "ava-result-item";

            const name = document.createElement("div");
            name.className = "ava-result-name";
            name.textContent = getAvaItemLabel(item);
            row.appendChild(name);

            const details = [];
            if (item.type) {
                details.push(item.type);
            }
            if (item.id !== undefined && item.id !== null) {
                details.push(`ID ${item.id}`);
            }
            if (item.created_at) {
                const createdAt = new Date(item.created_at);
                if (!Number.isNaN(createdAt.getTime())) {
                    details.push(createdAt.toLocaleString());
                }
            }
            if (item.path) {
                details.push(item.path);
            }
            if (item.match_source === "content") {
                details.push("Text match");
            }
            if (item.approximate_match) {
                details.push(item.approximate_match_source === "content"
                    ? "Close text match"
                    : "Close filename match");
            }
            if (Number.isFinite(Number(item.size))) {
                const size = Number(item.size);
                details.push(size < 1024
                    ? `${size} B`
                    : size < 1024 * 1024
                        ? `${(size / 1024).toFixed(1)} KB`
                        : `${(size / (1024 * 1024)).toFixed(1)} MB`);
            }
            if (item.modified_at) {
                const modifiedAt = new Date(item.modified_at);
                if (!Number.isNaN(modifiedAt.getTime())) {
                    details.push(`Modified ${modifiedAt.toLocaleString()}`);
                }
            }

            if (details.length) {
                const metadata = document.createElement("div");
                metadata.className = "ava-result-meta";
                metadata.textContent = details.join(" · ");
                row.appendChild(metadata);
            }

            if (item.content && item.title && item.content !== item.title) {
                const excerpt = document.createElement("div");
                excerpt.className = "ava-result-detail";
                const content = String(item.content).trim();
                excerpt.textContent = content.length > 180
                    ? `${content.slice(0, 177)}...`
                    : content;
                row.appendChild(excerpt);
            }

            if (item.snippet) {
                const excerpt = document.createElement("div");
                excerpt.className = "ava-result-detail";
                const snippet = String(item.snippet).trim();
                excerpt.textContent = snippet.length > 240
                    ? `${snippet.slice(0, 237)}...`
                    : snippet;
                row.appendChild(excerpt);
            }

            const url = getAvaItemUrl(item);
            if (url) {
                const link = document.createElement("a");
                link.className = "ava-result-link";
                link.href = url;
                link.target = "_blank";
                link.rel = "noopener noreferrer";
                link.textContent = "Open item";
                row.appendChild(link);
            }

            const summaryExtensions = new Set([
                "txt", "md", "markdown", "csv", "tsv", "json", "log",
                "py", "js", "ts", "html", "css", "xml", "yaml", "yml",
                "toml", "ini", "rst"
            ]);
            const localExtension = String(item.path || "").split(".").pop().toLowerCase();
            if (item.match_source && summaryExtensions.has(localExtension)) {
                const summarizeButton = document.createElement("button");
                summarizeButton.type = "button";
                summarizeButton.className = "ava-result-link ava-result-action";
                summarizeButton.textContent = "Summarize";
                summarizeButton.setAttribute("aria-label", "Summarize " + (item.name || item.path));
                summarizeButton.addEventListener("click", () => {
                    askAva("Summarize " + item.path);
                });
                row.appendChild(summarizeButton);
            }

            list.appendChild(row);
        });

        message.appendChild(list);

        if (validItems.length > 8) {
            const more = document.createElement("div");
            more.className = "ava-result-meta";
            more.textContent = `And ${validItems.length - 8} more item(s).`;
            message.appendChild(more);
        }

        appendAvaContent(message);
    }


    async function runAvaSearchAction(action, item) {
        try {
            const response = await fetch("/api/ava/search-action", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    action,
                    source: item.source,
                    path: item.path,
                    item_id: item.id
                })
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.message || "That action could not be completed.");
            }
            if (result.open_url) {
                window.open(result.open_url, "_blank", "noopener,noreferrer");
            }
            if (result.open_text) addAvaMessage(result.open_text);
            if (result.copy_text) {
                await navigator.clipboard.writeText(result.copy_text);
            }
            addAvaMessage(result.message || "Done.");
        } catch (error) {
            addAvaMessage(error.message || "That action could not be completed.");
        }
    }


    function addAvaSearchResults(result) {
        const items = Array.isArray(result.results) ? result.results : [];
        const message = document.createElement("div");
        message.className = "ava-message ava-message-ai ava-result-message";
        const heading = document.createElement("div");
        heading.className = "ava-result-heading";
        heading.textContent = `Search results (${Number(result.count) || 0})`;
        message.appendChild(heading);

        const list = document.createElement("div");
        list.className = "ava-result-list";
        const searchedPlaces = new Set(result.search_summary?.places || []);
        for (const [source, label] of [["stash", "In Stash"], ["mac", "On your Mac"]]) {
            const groupItems = items.filter(item => item && item.source === source);
            if (!searchedPlaces.has(label) && !groupItems.length) continue;
            const groupHeading = document.createElement("div");
            groupHeading.className = "ava-result-heading";
            const sourceCount = Number(result.source_counts?.[source]) || groupItems.length;
            groupHeading.textContent = `${label} (${sourceCount})`;
            list.appendChild(groupHeading);
            for (const item of groupItems) {
                const row = document.createElement("div");
                row.className = "ava-result-item";
                const name = document.createElement("div");
                name.className = "ava-result-name";
                name.textContent = String(item.name || "Untitled item");
                row.appendChild(name);

                const rawDate = item.created_at || item.modified_at;
                const parsedDate = rawDate ? new Date(rawDate) : null;
                const dateLabel = parsedDate && !Number.isNaN(parsedDate.getTime())
                    ? parsedDate.toLocaleString()
                    : "Date unavailable";
                const details = [item.type || "File", dateLabel, item.location || "Location unavailable"];
                if (Number.isFinite(Number(item.size))) {
                    const size = Number(item.size);
                    details.push(size < 1024 ? `${size} B` : size < 1024 * 1024
                        ? `${(size / 1024).toFixed(1)} KB`
                        : `${(size / (1024 * 1024)).toFixed(1)} MB`);
                } else details.push("Size unavailable");
                const metadata = document.createElement("div");
                metadata.className = "ava-result-meta";
                metadata.textContent = details.join(" · ");
                row.appendChild(metadata);
                if (item.content_preview) {
                    const excerpt = document.createElement("div");
                    excerpt.className = "ava-result-detail";
                    excerpt.textContent = String(item.content_preview);
                    row.appendChild(excerpt);
                }

                const openUrl = getAvaItemUrl(item);
                if (source === "mac" || openUrl || source === "stash") {
                    const open = document.createElement(source === "stash" && openUrl ? "a" : "button");
                    open.className = "ava-result-link ava-result-action";
                    open.textContent = "Open";
                    if (source === "mac" || !openUrl) {
                        open.type = "button";
                        open.addEventListener("click", () => runAvaSearchAction("open", item));
                    } else {
                        open.href = openUrl;
                        open.target = "_blank";
                        open.rel = "noopener noreferrer";
                    }
                    row.appendChild(open);
                }

                if (source === "mac" || item.has_file) {
                    const reveal = document.createElement("button");
                    reveal.type = "button";
                    reveal.className = "ava-result-link ava-result-action";
                    reveal.textContent = "Reveal in Finder";
                    reveal.addEventListener("click", () => runAvaSearchAction("reveal", item));
                    row.appendChild(reveal);
                }

                const copy = document.createElement("button");
                copy.type = "button";
                copy.className = "ava-result-link ava-result-action";
                copy.textContent = "Copy";
                copy.addEventListener("click", () => runAvaSearchAction("copy", item));
                row.appendChild(copy);

                if (source === "mac") {
                    const save = document.createElement("button");
                    save.type = "button";
                    save.className = "ava-result-link ava-result-action";
                    save.textContent = "Save to Stash";
                    save.addEventListener("click", () => runAvaSearchAction("save", item));
                    row.appendChild(save);
                }
                list.appendChild(row);
            }
        }
        message.appendChild(list);

        if (result.has_more) {
            const more = document.createElement("button");
            more.type = "button";
            more.className = "ava-result-link ava-result-action";
            more.textContent = "Show more";
            more.addEventListener("click", () => askAva("show more"));
            message.appendChild(more);
        }
        appendAvaContent(message);
    }


    function addAvaFileCopyPreview(preview) {
        const message = document.createElement("div");
        message.className = "ava-message ava-message-ai ava-result-message";

        const heading = document.createElement("div");
        heading.className = "ava-result-heading";
        heading.textContent = `Files to copy (${preview.moves.length})`;
        message.appendChild(heading);

        const destination = document.createElement("div");
        destination.className = "ava-result-meta";
        destination.textContent = `Date folder: ${preview.destination_folder}/${preview.date}`;
        message.appendChild(destination);

        const list = document.createElement("div");
        list.className = "ava-result-list";
        preview.moves.forEach(file => {
            const row = document.createElement("div");
            row.className = "ava-result-item";
            const name = document.createElement("div");
            name.className = "ava-result-name";
            name.textContent = file.file;
            row.appendChild(name);
            list.appendChild(row);
        });
        message.appendChild(list);

        const skipped = Array.isArray(preview.skipped) ? preview.skipped : [];
        if (skipped.length) {
            const skippedHeading = document.createElement("div");
            skippedHeading.className = "ava-result-heading";
            skippedHeading.textContent = "Skipped (not copied)";
            message.appendChild(skippedHeading);

            const skippedList = document.createElement("div");
            skippedList.className = "ava-result-list";
            skipped.forEach(file => {
                const row = document.createElement("div");
                row.className = "ava-result-item";
                const name = document.createElement("div");
                name.className = "ava-result-name";
                name.textContent = file.file || "File";
                row.appendChild(name);
                const reason = document.createElement("div");
                reason.className = "ava-result-meta";
                reason.textContent = file.reason || "Skipped";
                row.appendChild(reason);
                skippedList.appendChild(row);
            });
            message.appendChild(skippedList);
        }

        appendAvaContent(message);
    }


    function addAvaFileActionPreview(preview) {
        const items = Array.isArray(preview?.items) ? preview.items : [];
        const message = document.createElement("div");
        message.className = "ava-message ava-message-ai ava-result-message";
        const heading = document.createElement("div");
        heading.className = "ava-result-heading";
        heading.textContent = `Exact file preview (${items.length})`;
        message.appendChild(heading);
        const list = document.createElement("div");
        list.className = "ava-result-list";
        for (const item of items) {
            const row = document.createElement("div");
            row.className = "ava-result-item";
            const name = document.createElement("div");
            name.className = "ava-result-name";
            name.textContent = String(item.path || "File");
            row.appendChild(name);
            if (item.destination) {
                const destination = document.createElement("div");
                destination.className = "ava-result-meta";
                destination.textContent = `Destination: ${item.destination}${item.collision_suffix ? " (number added to avoid replacing a file)" : ""}`;
                row.appendChild(destination);
            }
            if (Number.isFinite(Number(item.size))) {
                const size = document.createElement("div");
                size.className = "ava-result-meta";
                size.textContent = `${Number(item.size).toLocaleString()} bytes`;
                row.appendChild(size);
            }
            list.appendChild(row);
        }
        message.appendChild(list);
        appendAvaContent(message);
    }


    function openAva() {
        showChatWorkspace();
        avaInput.focus();
    }


    function closeAva() {

        if (activeVoiceRecognition) {
            activeVoiceRecognition.abort();
        }
        if ("speechSynthesis" in window) {
            window.speechSynthesis.cancel();
        }

        showLibraryWorkspace();
    }


    async function askAva(command, inputMode = avaInputMode) {

        let attachmentContext = { names: [], context: "" };
        try {
            attachmentContext = await window.StashAvaAttachments?.prepareForSend?.() || attachmentContext;
        } catch (error) {
            addAvaMessage(error.message || "Remove the unreadable attachment or choose another file.");
            return;
        }

        const displayCommand = attachmentContext.names.length
            ? `${attachmentContext.names.map(name => `📎 ${name}`).join(" · ")}\n${command}`
            : command;
        addAvaMessage(displayCommand, "user");
        const requestConversationId = activeConversationId;
        const activeConversation = avaConversations.find(item => item.id === requestConversationId);
        const requestHistory = activeConversation
            ? activeConversation.messages.slice(0, -1).slice(-12).map(message => ({
                role: message.role,
                content: String(message.text || "").slice(0, 1800)
            }))
            : [];

        avaInput.value = "";
        avaInput.style.height = "auto";

        avaInput.disabled = true;
        avaVoiceButton.disabled = true;
        avaSendButton.disabled = true;
        avaTyping.hidden = false;
        avaStopButton.hidden = false;
        const requestController = new AbortController();
        activeRequestController = requestController;

        let requestCommand = attachmentContext.context
            ? `${command}\n\nUse this attachment context to answer the user's request:\n${attachmentContext.context}`
            : command;


        try {

            if (pendingFileCopyCommand && /^(cancel(?: it)?|stop|never mind|nevermind|forget it)$/i.test(command.trim())) {
                pendingFileCopyCommand = null;
                addAvaMessage("Okay, I won't continue that file-copy request.");
                return;
            }

            if (pendingFileCopyCommand) {
                requestCommand = `${pendingFileCopyCommand}\nThe user now provides these folder details: ${command}`;
            }

            const response = await fetch("/api/ava", {

                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    command: requestCommand,
                    conversation_id: requestConversationId,
                    history: requestHistory,
                    input_mode: inputMode,
                    search_context: activeConversation?.searchContext || null,
                    search_offset: Number(activeConversation?.searchOffset) || 0
                }),
                signal: requestController.signal

            });


            const result = await response.json();

            if (requestConversationId !== activeConversationId) return;

            if (result.needs_file_copy_paths) {
                pendingFileCopyCommand = requestCommand;
            } else {
                pendingFileCopyCommand = null;
            }


            if (!response.ok) {

                throw new Error(
                    result.message || "Ava request failed."
                );

            }


            addAvaMessage(
                result.message || "Done."
            );
            window.StashAvaAttachments?.clear?.();

            if (result.search_context) {
                const conversation = avaConversations.find(item => item.id === requestConversationId);
                if (conversation) {
                    conversation.searchContext = result.search_context;
                    conversation.searchOffset = result.offset + (result.results || []).length;
                    saveAvaConversations();
                }
                addAvaSearchResults(result);
            }

            if (voiceReplyMode) {
                window.dispatchEvent(new CustomEvent("stash:ava-voice-response"));
                speakAvaMessage(result.message || "Done.");
            }

            if (result.cancelled) {
                stopMobileActionPolling();
                avaConfirmation.hidden = true;
                pendingDeleteItem = null;
                pendingDeleteConfirmationToken = null;
                pendingConfirmationType = null;
                pendingOrganizeFilters = null;
                pendingFileOrganizationToken = null;
                pendingFileActionToken = null;
            }

            if (result.requires_confirmation) {

                if (avaConfirmYes) avaConfirmYes.disabled = false;
                if (avaConfirmNo) avaConfirmNo.disabled = false;

                pendingConfirmationType =
                    result.confirmation_type || null;

                pendingDeleteItem =
                    result.item || result.video || null;

                pendingDeleteConfirmationToken =
                    result.confirmation_type === "delete_item"
                        ? result.confirmation_token || null
                        : null;

                pendingOrganizeFilters =
                    result.organize_filters || null;

                pendingFileOrganizationToken =
                    result.confirmation_token || null;

                pendingFileActionToken = result.confirmation_type === "file_action"
                    ? result.confirmation_token || null
                    : null;
                pendingMobileActionId = result.confirmation_type === "file_action"
                    ? result.mobile_action_id || null
                    : null;

                const confirmationNote = avaConfirmation.querySelector(".confirmation-note");
                if (confirmationNote) {
                    confirmationNote.textContent = result.file_action_preview?.operation === "empty_trash"
                        ? "This permanently deletes files from Stash Trash. Review this separate action carefully."
                        : "Review this preview here or in the paired Android Action Inbox. Nothing changes until you approve it.";
                }
                if (avaConfirmYes) {
                    avaConfirmYes.textContent = result.file_action_preview?.operation === "empty_trash"
                        ? "Empty trash permanently"
                        : "Confirm";
                }

                avaConfirmation.hidden = false;
                if (pendingMobileActionId) watchMobileActionDecision(pendingMobileActionId);

            }

            if (result.file_copy_preview && Array.isArray(result.file_copy_preview.moves)) {
                addAvaFileCopyPreview(result.file_copy_preview);
            }

            if (result.file_action_preview && Array.isArray(result.file_action_preview.items)) {
                addAvaFileActionPreview(result.file_action_preview);
            }


            const resultArrays = result.search_context ? [] : [
                result.results,
                result.items,
                result.local_files,
                result.matches,
                result.preview && result.preview.items
            ];
            const returnedItems = resultArrays.find(
                items => Array.isArray(items) && items.length
            );
            const displayedItems = returnedItems || (
                result.item
                    ? [result.item]
                    : result.video && !result.requires_confirmation
                        ? [result.video]
                        : []
            );

            if (displayedItems.length) {
                const heading = Array.isArray(result.matches)
                    ? "Possible matches"
                    : Array.isArray(result.local_files)
                        ? "Files in folder"
                    : result.preview && result.preview.items
                        ? "Preview"
                        : "Saved items";
                addAvaResults(displayedItems, heading);
            }

        } catch (error) {

            if (error.name === "AbortError") {
                if (requestConversationId === activeConversationId) {
                    addAvaMessage("I stopped waiting for that reply. No confirmation was sent.");
                }
                return;
            }

            console.error("Ava error:", error);
            const errorMessage = error instanceof TypeError
                ? "I couldn't reach Stash's local server. Make sure Stash is running, then try again."
                : (error.message || "Ava couldn't complete that request. Try again.");
            addAvaMessage(errorMessage);
            if (voiceReplyMode) speakAvaMessage(errorMessage);

        } finally {

            avaTyping.hidden = true;
            avaStopButton.hidden = true;
            if (activeRequestController === requestController) {
                activeRequestController = null;
                avaInput.disabled = false;
                avaVoiceButton.disabled = false;
                avaSendButton.disabled = !avaInput.value.trim();
            }

            voiceReplyMode = false;
            avaInputMode = "text";

            avaInput.focus();

        }

    }


    avaToggle?.addEventListener(
        "click",
        openAva
    );


    avaLibraryVoiceButton?.addEventListener("click", requestAvaVoiceInput);

    avaClose?.addEventListener(
        "click",
        closeAva
    );


    avaStopButton?.addEventListener("click", () => {
        if (activeRequestController) activeRequestController.abort();
    });

    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && activeRequestController) {
            activeRequestController.abort();
        }
    });


    document.querySelectorAll(".suggestion-card").forEach(button => {
        button.addEventListener("click", () => {
            avaInput.value = button.dataset.prompt || "";
            avaInput.dispatchEvent(new Event("input", { bubbles: true }));
            avaInput.focus();
        });
    });


    function resizeAvaInput() {
        avaInput.style.height = "auto";
        avaInput.style.height = `${Math.min(avaInput.scrollHeight, 8 * 24)}px`;
        avaSendButton.disabled = !avaInput.value.trim() || avaInput.disabled;
    }


    avaInput.addEventListener("input", resizeAvaInput);
    avaInput.addEventListener("keydown", event => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            if (avaInput.value.trim()) avaForm.requestSubmit();
        }
    });
    resizeAvaInput();


    avaMessages.addEventListener("scroll", () => {
        const nearBottom = avaMessages.scrollHeight - avaMessages.scrollTop - avaMessages.clientHeight < 80;
        const scrollButton = document.getElementById("avaScrollBottom");
        if (scrollButton) scrollButton.hidden = nearBottom;
    });


    document.getElementById("avaScrollBottom")?.addEventListener("click", () => {
        avaMessages.scrollTo({ top: avaMessages.scrollHeight, behavior: "smooth" });
    });


    avaVoiceButton?.addEventListener(
        "click",
        beginAvaVoiceInput
    );


    avaForm?.addEventListener(
        "submit",
        async (event) => {

            event.preventDefault();

            if (activeVoiceRecognition) {
                activeVoiceRecognition.stop();
                avaVoiceStatus.textContent = "Finishing voice input…";
                return;
            }

            const command = avaInput.value.trim();

            if (!command) {
                return;
            }

            await askAva(command, avaInputMode);

        }
    );


    avaConfirmYes?.addEventListener(
        "click",
        async () => {

            stopMobileActionPolling();

            addAvaMessage("Yes");

            try {

                let url;
                let body = {};

                if (pendingConfirmationType === "organize_files") {

                    if (!pendingFileOrganizationToken) {
                        throw new Error("The file-organization preview has expired. Please try again.");
                    }

                    url = "/api/ava/confirm-organize-files";
                    body = {
                        confirmation_token: pendingFileOrganizationToken
                    };

                } else if (pendingConfirmationType === "file_action") {

                    if (!pendingFileActionToken) {
                        throw new Error("This file-action preview has expired. Please ask Ava again.");
                    }

                    url = "/api/ava/file-action/confirm";
                    body = { confirmation_token: pendingFileActionToken };

                } else if (pendingConfirmationType === "copy_files") {

                    if (!pendingFileOrganizationToken) {
                        throw new Error("The file-copy preview has expired. Please try again.");
                    }

                    url = "/api/ava/confirm-copy-files";
                    body = {
                        confirmation_token: pendingFileOrganizationToken
                    };

                } else if (
                    pendingConfirmationType === "organize_items" ||
                    pendingConfirmationType === "arrange_today"
                ) {

                    url = "/api/ava/confirm-arrange";
                    body = {
                        filters: pendingOrganizeFilters || {}
                    };

                } else {

                    if (!pendingDeleteItem || pendingDeleteItem.id === undefined) {
                        return;
                    }
                    if (
                        pendingConfirmationType === "delete_item" &&
                        !pendingDeleteConfirmationToken
                    ) {
                        throw new Error("The delete preview has expired. Please ask Ava again.");
                    }

                    url = "/api/ava/confirm-delete";

                    body = {
                        item_id: pendingDeleteItem.id,
                        confirmation_token: pendingDeleteConfirmationToken
                    };

                }

                const response = await fetch(url, {

                    method: "POST",

                    headers: {
                        "Content-Type": "application/json"
                    },

                    body: JSON.stringify(body)

                });


                const result = await response.json();


                if (!response.ok) {

                    throw new Error(
                        result.message || "Action failed."
                    );

                }


                addAvaMessage(
                    result.message || "Done."
                );


                avaConfirmation.hidden = true;
                pendingDeleteItem = null;
                pendingDeleteConfirmationToken = null;
                pendingConfirmationType = null;
                pendingOrganizeFilters = null;
                pendingFileOrganizationToken = null;
                pendingFileActionToken = null;
                pendingMobileActionId = null;

                loadClipboard();

            } catch (error) {

                console.error(
                    "Ava confirmation error:",
                    error
                );

                addAvaMessage(
                    "I couldn't complete that action. You can try again."
                );

                avaConfirmation.hidden = false;

            }

        }
    );


    avaConfirmNo?.addEventListener(
        "click",
        async () => {

            stopMobileActionPolling();

            if (
                pendingConfirmationType === "delete_item" &&
                pendingDeleteConfirmationToken
            ) {
                try {
                    const response = await fetch("/api/ava/confirm-delete", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            confirmation_token: pendingDeleteConfirmationToken,
                            cancel: true
                        })
                    });
                    const result = await response.json();
                    if (!response.ok) {
                        throw new Error(result.message || "Cancellation failed.");
                    }
                } catch (error) {
                    console.error("Ava delete cancellation error:", error);
                    addAvaMessage("I couldn't cancel that delete preview. Please try again.");
                    return;
                }
            }

            if (
                pendingConfirmationType === "organize_files" &&
                pendingFileOrganizationToken
            ) {
                try {
                    const response = await fetch(
                        "/api/ava/cancel-organize-files",
                        {
                            method: "POST",
                            headers: {
                                "Content-Type": "application/json"
                            },
                            body: JSON.stringify({
                                confirmation_token: pendingFileOrganizationToken
                            })
                        }
                    );

                    const result = await response.json();
                    if (!response.ok) {
                        throw new Error(result.message || "Cancellation failed.");
                    }
                } catch (error) {
                    console.error("Ava file-organization cancellation error:", error);
                    addAvaMessage(
                        "I couldn't cancel the file-organization preview. Please try again."
                    );
                    return;
                }
            }

            if (
                pendingConfirmationType === "copy_files" &&
                pendingFileOrganizationToken
            ) {
                try {
                    const response = await fetch("/api/ava/cancel-copy-files", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            confirmation_token: pendingFileOrganizationToken
                        })
                    });
                    const result = await response.json();
                    if (!response.ok) {
                        throw new Error(result.message || "Cancellation failed.");
                    }
                } catch (error) {
                    console.error("Ava file-copy cancellation error:", error);
                    addAvaMessage("I couldn't cancel the file-copy preview. Please try again.");
                    return;
                }
            }

            if (pendingConfirmationType === "file_action" && pendingFileActionToken) {
                try {
                    const response = await fetch("/api/ava/file-action/cancel", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ confirmation_token: pendingFileActionToken })
                    });
                    const result = await response.json();
                    if (!response.ok) throw new Error(result.message || "Cancellation failed.");
                } catch (error) {
                    console.error("Ava file-action cancellation error:", error);
                    addAvaMessage("I couldn't cancel that file preview. No files were changed.");
                    return;
                }
            }

            avaConfirmation.hidden = true;

            pendingDeleteItem = null;
            pendingDeleteConfirmationToken = null;
            pendingConfirmationType = null;
            pendingOrganizeFilters = null;
            pendingFileOrganizationToken = null;
            pendingFileActionToken = null;
            pendingMobileActionId = null;

            addAvaMessage(
                "Okay, I won't do that."
            );

        }
    );

})();
