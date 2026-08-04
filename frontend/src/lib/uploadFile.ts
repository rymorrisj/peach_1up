import { getCsrfToken } from '@/api/client';

const baseURL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';

export interface FileUploadHandle<T> {
  promise: Promise<T>;
  abort: () => void;
}

// XHR is required here — fetch() does not expose upload progress events.
export function uploadFile<T>(
  path: string,
  file: File,
  onProgress: (pct: number) => void,
): FileUploadHandle<T> {
  const fd = new FormData();
  fd.append('file', file);

  const xhr = new XMLHttpRequest();
  const promise = new Promise<T>((resolve, reject) => {
    xhr.open('POST', `${baseURL}${path}`);
    xhr.withCredentials = true;
    xhr.setRequestHeader('X-CSRF-Token', getCsrfToken());

    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) onProgress(Math.round((ev.loaded / ev.total) * 100));
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as T);
        } catch {
          reject(new Error('Upload succeeded but the response could not be parsed.'));
        }
        return;
      }
      try {
        const body = JSON.parse(xhr.responseText) as { detail?: string };
        reject(new Error(body.detail ?? `Upload failed (HTTP ${xhr.status}).`));
      } catch {
        reject(new Error(`Upload failed (HTTP ${xhr.status}).`));
      }
    };

    xhr.onerror = () => reject(new Error('Network error during upload.'));
    xhr.onabort = () => reject(new Error('Upload cancelled.'));

    xhr.send(fd);
  });

  return { promise, abort: () => xhr.abort() };
}
