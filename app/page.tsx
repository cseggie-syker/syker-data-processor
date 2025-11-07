import { FileUploadForm } from "../components/FileUploadForm";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col items-center px-6 py-16">
      <header className="text-center">
        <p className="text-sm font-semibold uppercase tracking-wide text-sky-600">
          Syker Systems
        </p>
        <h1 className="mt-3 text-4xl font-bold text-slate-900">
          Convert Syker DTL files into Excel in seconds
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-slate-600">
          Upload raw telemetry exports and receive organized Excel workbooks ready for reporting and
          analysis. No installation required.
        </p>
      </header>

      <section className="mt-12 w-full">
        <FileUploadForm />
      </section>

      <section className="mt-16 grid gap-6 text-sm text-slate-600 md:grid-cols-3">
        <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-base font-semibold text-slate-800">Flexible inputs</h3>
          <p className="mt-2">
            Drop individual `.dtl` files or zip entire folders. The service automatically detects
            supported data logs.
          </p>
        </article>
        <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-base font-semibold text-slate-800">Organized output</h3>
          <p className="mt-2">
            Each dataset is exported to Excel with descriptive column names, grouped by data type in
            the final ZIP download.
          </p>
        </article>
        <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-base font-semibold text-slate-800">Secure & disposable</h3>
          <p className="mt-2">
            Files are processed in ephemeral serverless containers and never stored once the download
            completes.
          </p>
        </article>
      </section>
    </main>
  );
}


