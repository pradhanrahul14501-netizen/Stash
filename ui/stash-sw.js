"use strict";

self.addEventListener("install", event => {
    event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", event => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", event => {
    const requestUrl = new URL(event.request.url);
    if (event.request.method !== "POST" || requestUrl.pathname !== "/share-target") {
        return;
    }

    event.respondWith((async () => {
        const destination = new URL("/", self.location.origin);
        try {
            const formData = await event.request.formData();
            const response = await fetch("/api/shared/share", {
                method: "POST",
                body: formData,
                credentials: "same-origin",
            });
            const payload = await response.json().catch(() => ({}));
            if (response.ok && payload.success) {
                destination.searchParams.set(
                    "share",
                    payload.kind === "link" ? "link" : "saved",
                );
            } else {
                destination.searchParams.set(
                    "share",
                    response.status === 401 ? "login" : "error",
                );
            }
        } catch {
            destination.searchParams.set("share", "error");
        }
        return Response.redirect(destination.toString(), 303);
    })());
});
