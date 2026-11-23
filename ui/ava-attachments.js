/* STASH-AVA-ATTACHMENTS: read user-selected files in memory and expose text context to Ava. */
(() => {
    "use strict";

    const picker = document.getElementById("avaAttachmentInput");
    const attachButton = document.getElementById("avaLibraryButton");
    const chips = document.getElementById("avaAttachments");
    const messageInput = document.getElementById("avaInput");
    const MAX_FILE_BYTES = 20 * 1024 * 1024;
    const MAX_ATTACHMENTS = 10;
    const MAX_CONTEXT_CHARS = 180_000;
    const attachments = [];
    let nextId = 0;

    if (!picker || !attachButton || !chips) return;

    const formatSize = bytes => {
        if (!Number.isFinite(bytes) || bytes < 0) return "Unknown size";
        if (bytes < 1024) return `${bytes} B`;
        const units = ["KB", "MB", "GB"];
        let value = bytes / 1024;
        let unit = 0;
        while (value >= 1024 && unit < units.length - 1) {
            value /= 1024;
            unit += 1;
        }
        return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
    };

    function render() {
        chips.replaceChildren();
        chips.hidden = attachments.length === 0;
        for (const attachment of attachments) {
            const chip = document.createElement("div");
            chip.className = "ava-attachment-chip";
            chip.setAttribute("role", "listitem");
            chip.dataset.state = attachment.status;

            const details = document.createElement("span");
            details.className = "ava-attachment-details";
            const name = document.createElement("strong");
            name.textContent = attachment.name;
            name.title = attachment.name;
            const status = document.createElement("small");
            status.textContent = attachment.status === "loading"
                ? "Reading…"
                : attachment.status === "error"
                    ? attachment.error
                    : `${attachment.kind} · ${formatSize(attachment.size)}`;
            details.append(name, status);

            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "ava-attachment-remove";
            remove.textContent = "×";
            remove.setAttribute("aria-label", `Remove ${attachment.name}`);
            remove.addEventListener("click", () => removeAttachment(attachment.id));
            chip.append(details, remove);
            chips.append(chip);
        }
        document.dispatchEvent(new CustomEvent("stash:ava-attachments-changed"));
    }

    function removeAttachment(id) {
        const index = attachments.findIndex(item => item.id === id);
        if (index < 0) return;
        attachments[index].controller?.abort();
        attachments.splice(index, 1);
        render();
    }

    function classify(file) {
        const name = file.name.toLowerCase();
        const mime = (file.type || "").toLowerCase();
        if (mime.startsWith("image/") || /\.(avif|bmp|gif|heic|heif|jpe?g|png|svg|tiff?|webp)$/.test(name)) return "Image details";
        if (mime.startsWith("video/") || /\.(avi|m4v|mkv|mov|mp4|mpeg|mpg|webm)$/.test(name)) return "Video details";
        if (/\.(pdf)$/.test(name)) return "PDF";
        if (/\.(docx)$/.test(name)) return "Word document";
        if (/\.(txt|md|markdown|rst|csv|tsv|json|jsonl|xml|ya?ml|toml|ini|cfg|conf|log|py|pyw|js|jsx|ts|tsx|html?|css|scss|less|c|h|cc|cpp|hpp|java|kt|swift|go|rs|rb|php|sh|zsh|bash|sql|vue|svelte|ipynb)$/.test(name) || mime.startsWith("text/")) {
            return "Text or code";
        }
        return "Unsupported file";
    }

    async function readText(attachment) {
        if (attachment.size > MAX_FILE_BYTES) {
            throw new Error("Over 20 MB. Choose a smaller file.");
        }
        const body = new FormData();
        body.append("file", attachment.file, attachment.name);
        attachment.controller = new AbortController();
        const timeout = window.setTimeout(() => attachment.controller.abort(), 120_000);
        try {
            const response = await fetch("/api/ava/extract-attachment", {
                method: "POST",
                body,
                signal: attachment.controller.signal,
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.message || "Stash could not read this file.");
            attachment.text = result.text || "";
            attachment.truncated = Boolean(result.truncated);
            attachment.status = "ready";
        } catch (error) {
            if (error.name === "AbortError" && attachment.removed) return;
            attachment.status = "error";
            attachment.error = error.name === "AbortError"
                ? "Reading took too long. Try a smaller file."
                : error.message || "Could not read this file.";
        } finally {
            window.clearTimeout(timeout);
            attachment.controller = null;
            render();
        }
    }

    function addFile(file) {
        const kind = classify(file);
        const attachment = {
            id: ++nextId,
            file,
            name: file.name || "Untitled file",
            size: Number(file.size) || 0,
            mime: file.type || "application/octet-stream",
            kind,
            status: "ready",
            text: "",
        };
        attachments.push(attachment);

        if (attachments.length > MAX_ATTACHMENTS) {
            attachment.status = "error";
            attachment.error = "Attach up to 10 files at a time.";
        } else if (attachment.size > MAX_FILE_BYTES) {
            attachment.status = "error";
            attachment.error = "Over 20 MB. Choose a smaller file.";
        } else if (kind === "Unsupported file") {
            attachment.status = "error";
            attachment.error = "This file type isn’t supported.";
        } else if (kind === "Text or code" || kind === "PDF" || kind === "Word document") {
            attachment.status = "loading";
            attachment.ready = readText(attachment);
        }
        render();
    }

    attachButton.addEventListener("click", () => picker.click());
    picker.addEventListener("change", () => {
        const selected = Array.from(picker.files || []);
        picker.value = "";
        if (!selected.length) return;
        selected.forEach(addFile);
        if (messageInput && !messageInput.value.trim()) {
            const onlyMetadata = selected.every(file => {
                const name = (file.name || "").toLowerCase();
                return /^(image|video)\//i.test(file.type || "")
                    || /\.(avif|bmp|gif|heic|heif|jpe?g|png|svg|tiff?|webp|avi|m4v|mkv|mov|mp4|mpeg|mpg|webm)$/.test(name);
            });
            messageInput.value = onlyMetadata ? "Tell me about the attached file details" : "Summarize the attached file";
            messageInput.dispatchEvent(new Event("input", { bubbles: true }));
            messageInput.focus();
        }
    });

    window.StashAvaAttachments = Object.freeze({
        async prepareForSend() {
            await Promise.all(attachments.map(item => item.ready).filter(Boolean));
            const failed = attachments.find(item => item.status === "error");
            if (failed) throw new Error(`${failed.name}: ${failed.error} Remove it or choose another file.`);
            let remainingContext = MAX_CONTEXT_CHARS;
            return {
                names: attachments.map(item => item.name),
                context: attachments.map(item => {
                    const metadata = `File: ${item.name}\nType: ${item.mime || item.kind}\nSize: ${formatSize(item.size)}.`;
                    if (item.text) {
                        const text = item.text.slice(0, Math.max(0, remainingContext));
                        remainingContext -= text.length;
                        const truncated = item.truncated || text.length < item.text.length;
                        return text
                            ? `${metadata}\nExtracted text:\n${text}${truncated ? "\n[Text was shortened to fit Ava's context.]" : ""}`
                            : `${metadata}\nText was omitted because the attachment context limit was reached.`;
                    }
                    return `${metadata}\nOnly the file metadata is available to Ava; its image or video contents were not uploaded.`;
                }).join("\n\n---\n\n"),
            };
        },
        clear() {
            attachments.splice(0).forEach(item => item.controller?.abort());
            render();
        },
    });
})();
