"use client";

import { ArrowDownTrayIcon, DocumentArrowUpIcon } from "@heroicons/react/24/outline";
import clsx from "clsx";
import { useCallback, useEffect, useRef, useState } from "react";

import { processUpload } from "../lib/api";

type FileWithRelativePath = File & { webkitRelativePath?: string };

interface FileSystemEntryBaseLike {
  isFile: boolean;
  isDirectory: boolean;
  name: string;
  fullPath: string;
}

interface FileSystemFileEntryLike extends FileSystemEntryBaseLike {
  isFile: true;
  isDirectory: false;
  file: (
    successCallback: (file: File) => void,
    errorCallback?: (error: DOMException) => void,
  ) => void;
}

interface FileSystemDirectoryEntryLike extends FileSystemEntryBaseLike {
  isFile: false;
  isDirectory: true;
  createReader: () => FileSystemDirectoryReader;
}

interface FileSystemDirectoryReader {
  readEntries: (
    successCallback: (entries: FileSystemEntryLike[]) => void,
    errorCallback?: (error: DOMException) => void,
  ) => void;
}

type FileSystemEntryLike = FileSystemFileEntryLike | FileSystemDirectoryEntryLike;

async function readAllDirectoryEntries(reader: FileSystemDirectoryReader): Promise<FileSystemEntryLike[]> {
  const entries: FileSystemEntryLike[] = [];

  return new Promise<FileSystemEntryLike[]>((resolve, reject) => {
    const readEntries = () => {
      reader.readEntries((batch) => {
        if (!batch.length) {
          resolve(entries);
          return;
        }

        entries.push(...batch);
        readEntries();
      }, reject);
    };

    readEntries();
  });
}

async function traverseEntry(entry: FileSystemEntryLike): Promise<File[]> {
  if (entry.isFile) {
    return new Promise<File[]>((resolve, reject) => {
      (entry as FileSystemFileEntryLike).file(
        (file) => {
          const relativePath = entry.fullPath.replace(/^\//, "");
          try {
            Object.defineProperty(file, "webkitRelativePath", {
              value: relativePath,
              configurable: true,
            });
          } catch {
            // Some browsers prevent redefining the property – ignore.
          }

          resolve([file]);
        },
        (error) => reject(error),
      );
    });
  }

  if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntryLike).createReader();
    const childEntries = await readAllDirectoryEntries(reader);
    const nested = await Promise.all(childEntries.map(traverseEntry));
    return nested.flat();
  }

  return [];
}

async function collectFilesFromItems(items: DataTransferItemList): Promise<File[]> {
  const entries = Array.from(items)
    .map((item) => {
      if (item.kind !== "file") return null;
      const getAsEntry = (item as DataTransferItem & { webkitGetAsEntry?: () => unknown }).webkitGetAsEntry;
      if (typeof getAsEntry !== "function") {
        return null;
      }

      const entry = getAsEntry() as FileSystemEntryLike | null | undefined;
      if (!entry) {
        return null;
      }

      return entry as FileSystemEntryLike;
    })
    .filter((entry): entry is FileSystemEntryLike => entry !== null);

  if (!entries.length) {
    return [];
  }

  const files = await Promise.all(entries.map(traverseEntry));
  return files.flat();
}

function getFileKey(file: FileWithRelativePath): string {
  return file.webkitRelativePath && file.webkitRelativePath.length > 0 ? file.webkitRelativePath : file.name;
}

type UploadStatus = "idle" | "uploading" | "success" | "error";

interface Props {
  className?: string;
}

export function FileUploadForm({ className }: Props) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [status, setStatus] = useState<UploadStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (fileInputRef.current) {
      fileInputRef.current.setAttribute("webkitdirectory", "");
      fileInputRef.current.setAttribute("directory", "");
      fileInputRef.current.multiple = true;
    }
  }, []);

  const mergeFiles = useCallback((incoming: File[]) => {
    setSelectedFiles((prev) => {
      const map = new Map<string, File>();
      prev.forEach((file) => {
        map.set(getFileKey(file as FileWithRelativePath), file);
      });
      incoming.forEach((file) => {
        map.set(getFileKey(file as FileWithRelativePath), file);
      });
      return Array.from(map.values());
    });
  }, []);

  const reset = useCallback(() => {
    setSelectedFiles([]);
    setStatus("idle");
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, []);

  const onFilesSelected = useCallback(
    (files: FileList | File[] | null) => {
      if (!files) return;
      const list = Array.isArray(files) ? files : Array.from(files);
      if (!list.length) return;
      mergeFiles(list);
      setStatus("idle");
      setError(null);
    },
    [mergeFiles],
  );

  const onDrop = useCallback(
    async (event: React.DragEvent<HTMLLabelElement>) => {
      event.preventDefault();
      event.stopPropagation();
      const { items, files } = event.dataTransfer;

      try {
        if (items && items.length > 0) {
          const collected = await collectFilesFromItems(items);
          if (collected.length) {
            mergeFiles(collected);
            setStatus("idle");
            setError(null);
            return;
          }
        }

        if (files && files.length > 0) {
          onFilesSelected(files);
        }
      } catch (err) {
        console.error("Folder drop failed", err);
        if (files && files.length > 0) {
          onFilesSelected(files);
          setError(null);
          setStatus("idle");
        } else {
          setError(
            "We couldn't read one of the dropped items. Please zip the folder first or use the Browse button.",
          );
          setStatus("error");
        }
      } finally {
        event.dataTransfer.clearData();
      }
    },
    [mergeFiles, onFilesSelected],
  );

  const onSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!selectedFiles.length) return;

      setStatus("uploading");
      setError(null);

      try {
        await processUpload(selectedFiles);
        setStatus("success");
        reset();
      } catch (err) {
        let message = err instanceof Error ? err.message : "Upload failed. Please try again.";
        if (message === "Failed to fetch") {
          message = "Failed to fetch. If you uploaded a folder, please zip it before retrying.";
        }
        setError(message);
        setStatus("error");
      }
    },
    [selectedFiles, reset],
  );

  return (
    <form
      className={clsx("w-full max-w-3xl space-y-6", className)}
      onSubmit={onSubmit}
      aria-label="Syker DTL upload form"
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".dtl,.zip"
        hidden
        onChange={(event) => onFilesSelected(event.target.files)}
      />

      <label
        htmlFor="dtl-upload"
        onDrop={onDrop}
        onDragOver={(event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
        }}
        className={clsx(
          "flex min-h-[200px] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed",
          "border-slate-300 bg-white px-6 py-10 text-center shadow-sm transition hover:border-sky-400 hover:bg-sky-50",
        )}
      >
        <DocumentArrowUpIcon className="h-12 w-12 text-sky-500" aria-hidden="true" />
        <p className="mt-4 text-lg font-semibold text-slate-800">Drag & drop files or folders</p>
        <p className="mt-2 text-sm text-slate-500">
          Add `.dtl` files, zipped archives, or entire folders. Combine multiple uploads in one
          conversion.
        </p>
        <button
          type="button"
          className="mt-6 rounded-full bg-sky-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-sky-500"
          onClick={() => fileInputRef.current?.click()}
        >
          Browse files or folders
        </button>
      </label>

      {selectedFiles.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="text-sm font-medium text-slate-700">Files ready to convert</h3>
          <ul className="mt-2 max-h-48 space-y-1 overflow-auto text-sm text-slate-600">
            {selectedFiles.map((file) => {
              const displayName = (file as FileWithRelativePath).webkitRelativePath || file.name;
              return (
                <li key={getFileKey(file as FileWithRelativePath)} className="truncate" title={displayName}>
                  {displayName}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={!selectedFiles.length || status === "uploading"}
          className={clsx(
            "inline-flex items-center gap-2 rounded-full bg-sky-600 px-6 py-3 text-sm font-semibold text-white",
            "shadow-sm transition hover:bg-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-2",
          )}
        >
          <ArrowDownTrayIcon className="h-5 w-5" aria-hidden="true" />
          {status === "uploading" ? "Processing…" : "Convert to Excel"}
        </button>
        <button
          type="button"
          onClick={reset}
          className="text-sm font-medium text-slate-500 hover:text-slate-700"
        >
          Reset
        </button>
      </div>
    </form>
  );
}


