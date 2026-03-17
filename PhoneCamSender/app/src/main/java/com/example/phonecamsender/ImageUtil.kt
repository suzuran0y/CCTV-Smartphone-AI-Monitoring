package com.example.phonecamsender

import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import androidx.camera.core.ImageProxy
import java.io.ByteArrayOutputStream

object ImageUtil {

    fun yuvToJpeg(image: ImageProxy, quality: Int = 55): ByteArray {
        val nv21 = yuv420888ToNv21(image)

        val crop = image.cropRect
        val yuvImage = YuvImage(
            nv21,
            ImageFormat.NV21,
            crop.width(),
            crop.height(),
            null
        )

        val out = ByteArrayOutputStream()
        yuvImage.compressToJpeg(
            Rect(0, 0, crop.width(), crop.height()),
            quality.coerceIn(1, 100),
            out
        )
        return out.toByteArray()
    }

    private fun yuv420888ToNv21(image: ImageProxy): ByteArray {
        val crop = image.cropRect
        val format = image.format
        require(format == ImageFormat.YUV_420_888) {
            "Unsupported image format: $format"
        }

        val width = crop.width()
        val height = crop.height()

        val ySize = width * height
        val uvSize = width * height / 2
        val out = ByteArray(ySize + uvSize)

        val planes = image.planes
        val yPlane = planes[0]
        val uPlane = planes[1]
        val vPlane = planes[2]

        val yBuffer = yPlane.buffer
        val uBuffer = uPlane.buffer
        val vBuffer = vPlane.buffer

        val yRowStride = yPlane.rowStride
        val yPixelStride = yPlane.pixelStride

        val uRowStride = uPlane.rowStride
        val uPixelStride = uPlane.pixelStride

        val vRowStride = vPlane.rowStride
        val vPixelStride = vPlane.pixelStride

        // Copy Y plane
        var outputOffset = 0
        val yShift = 0
        val yHeight = height
        val yWidth = width

        for (row in 0 until yHeight) {
            val rowStart = yBuffer.position() + (row + crop.top) * yRowStride + crop.left * yPixelStride
            for (col in 0 until yWidth) {
                out[outputOffset++] = yBuffer.get(rowStart + col * yPixelStride)
            }
        }

        // Copy UV planes into NV21 layout: VU VU VU...
        val chromaHeight = height / 2
        val chromaWidth = width / 2

        for (row in 0 until chromaHeight) {
            val uRowStart = uBuffer.position() + (row + crop.top / 2) * uRowStride + (crop.left / 2) * uPixelStride
            val vRowStart = vBuffer.position() + (row + crop.top / 2) * vRowStride + (crop.left / 2) * vPixelStride

            for (col in 0 until chromaWidth) {
                val vValue = vBuffer.get(vRowStart + col * vPixelStride)
                val uValue = uBuffer.get(uRowStart + col * uPixelStride)

                out[outputOffset++] = vValue
                out[outputOffset++] = uValue
            }
        }

        return out
    }
}