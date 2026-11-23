package com.stash.app.data

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import java.io.File
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Extracts searchable text from imported images and PDFs using the bundled on-device OCR model. */
class LibraryTextIndexer {
    private val recognizer by lazy { TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS) }

    fun isSupported(mimeType: String, displayName: String): Boolean =
        mimeType.startsWith("image/", ignoreCase = true) ||
            mimeType.equals("application/pdf", ignoreCase = true) ||
            displayName.endsWith(".pdf", ignoreCase = true)

    suspend fun extract(file: File, mimeType: String, displayName: String): String =
        withContext(Dispatchers.IO) {
            when {
                mimeType.startsWith("image/", ignoreCase = true) -> recognizeImage(file)
                mimeType.equals("application/pdf", ignoreCase = true) ||
                    displayName.endsWith(".pdf", ignoreCase = true) -> recognizePdf(file)
                else -> ""
            }.take(MAX_INDEXED_CHARACTERS)
        }

    private suspend fun recognizeImage(file: File): String {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.absolutePath, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return ""

        var sampleSize = 1
        while (maxOf(bounds.outWidth, bounds.outHeight) / sampleSize > MAX_IMAGE_DIMENSION) {
            sampleSize *= 2
        }
        val bitmap = BitmapFactory.decodeFile(
            file.absolutePath,
            BitmapFactory.Options().apply { inSampleSize = sampleSize },
        ) ?: return ""
        return try {
            recognize(bitmap)
        } finally {
            bitmap.recycle()
        }
    }

    private suspend fun recognizePdf(file: File): String {
        val result = StringBuilder()
        ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { descriptor ->
            PdfRenderer(descriptor).use { renderer ->
                val pagesToIndex = minOf(renderer.pageCount, MAX_PDF_PAGES)
                for (pageNumber in 0 until pagesToIndex) {
                    if (result.length >= MAX_INDEXED_CHARACTERS) break
                    val page = renderer.openPage(pageNumber)
                    try {
                        val scale = minOf(
                            MAX_PDF_DIMENSION.toFloat() / page.width,
                            MAX_PDF_DIMENSION.toFloat() / page.height,
                        ).coerceAtMost(1f)
                        val bitmap = Bitmap.createBitmap(
                            (page.width * scale).toInt().coerceAtLeast(1),
                            (page.height * scale).toInt().coerceAtLeast(1),
                            Bitmap.Config.ARGB_8888,
                        )
                        try {
                            page.render(
                                bitmap,
                                null,
                                Matrix().apply { setScale(scale, scale) },
                                PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY,
                            )
                            val text = recognize(bitmap)
                            if (text.isNotBlank()) {
                                if (result.isNotEmpty()) result.append('\n')
                                result.append(text.take(MAX_INDEXED_CHARACTERS - result.length))
                            }
                        } finally {
                            bitmap.recycle()
                        }
                    } finally {
                        page.close()
                    }
                }
            }
        }
        return result.toString()
    }

    private suspend fun recognize(bitmap: Bitmap): String = suspendCoroutine { continuation ->
        recognizer.process(InputImage.fromBitmap(bitmap, 0))
            .addOnSuccessListener { result -> continuation.resume(result.text) }
            .addOnFailureListener { error -> continuation.resumeWithException(error) }
    }

    private companion object {
        const val MAX_IMAGE_DIMENSION = 2_400
        const val MAX_PDF_DIMENSION = 1_800
        const val MAX_PDF_PAGES = 100
        const val MAX_INDEXED_CHARACTERS = 100_000
    }
}
