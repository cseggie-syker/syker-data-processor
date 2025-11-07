type FileWithRelativePath = File & { webkitRelativePath?: string };

function deriveArchiveLabel(files: FileWithRelativePath[]): string | undefined {
  for (const file of files) {
    const relativePath = file.webkitRelativePath;
    if (relativePath) {
      const root = relativePath.split(/\\|\//)[0];
      if (root) {
        return root;
      }
    }
  }

  if (files.length > 0) {
    const base = files[0].name.replace(/\.[^.]+$/, "").trim();
    if (base) {
      return base;
    }
  }

  return undefined;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");

export async function processUpload(files: File[]): Promise<void> {
  const formData = new FormData();
  const filesWithRelativePath = files as FileWithRelativePath[];
  filesWithRelativePath.forEach((file) => {
    formData.append("files", file, file.name);
  });

  const archiveLabel = deriveArchiveLabel(filesWithRelativePath);
  if (archiveLabel) {
    formData.append("archive_label", archiveLabel);
  }

  const endpoint = API_BASE ? `${API_BASE}/process` : "/api/process";

  const response = await fetch(endpoint, {
    method: "POST",
    body: formData,
    mode: "cors",
  });

  if (!response.ok) {
    const text = await response.text();
    const message = text || `Server rejected the upload (status ${response.status}).`;
    throw new Error(message);
  }

  const blob = await response.blob();
  const filename = response.headers.get("Content-Disposition")?.split("filename=")[1]?.replace(/"/g, "");
  const downloadName = filename || "syker-processed-data.zip";

  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = downloadName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}


