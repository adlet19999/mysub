export type CompressionOptions = {
  maxWidth?: number;
  maxHeight?: number;
  quality?: number;
};

// Compresses uploaded images in browser before sending base64 to backend.
export async function compressImageFileToDataUrl(file: File, options: CompressionOptions = {}): Promise<string> {
  const maxWidth = options.maxWidth ?? 1280;
  const maxHeight = options.maxHeight ?? 1280;
  const quality = options.quality ?? 0.78;

  const originalDataUrl = await readFileAsDataUrl(file);
  const bitmap = await createImageBitmap(file);

  try {
    const ratio = Math.min(maxWidth / bitmap.width, maxHeight / bitmap.height, 1);
    const targetWidth = Math.max(1, Math.round(bitmap.width * ratio));
    const targetHeight = Math.max(1, Math.round(bitmap.height * ratio));

    const canvas = document.createElement("canvas");
    canvas.width = targetWidth;
    canvas.height = targetHeight;

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return originalDataUrl;
    }

    ctx.drawImage(bitmap, 0, 0, targetWidth, targetHeight);
    const compressedDataUrl = canvas.toDataURL("image/webp", quality);

    if (!compressedDataUrl || compressedDataUrl.length >= originalDataUrl.length) {
      return originalDataUrl;
    }

    return compressedDataUrl;
  } finally {
    bitmap.close();
  }
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve(typeof reader.result === "string" ? reader.result : "");
    };
    reader.onerror = () => {
      reject(reader.error ?? new Error("Failed to read file"));
    };
    reader.readAsDataURL(file);
  });
}
