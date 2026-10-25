import React from 'react';
import { ArrowUpRight, CloudSun, MapPinned } from 'lucide-react';
import { platformDestinations } from '../../lib/platformDestinations';

export const PlatformDestinationsSection: React.FC = () => (
  <section
    id="section-platform-destinations"
    aria-labelledby="platform-destinations-title"
    className="scroll-mt-24 border-y border-[#E5E7EB] bg-[#FAFAFA] px-4 py-14 sm:px-6 sm:py-16 lg:px-8"
  >
    <div className="mx-auto max-w-7xl">
      <div className="mb-8 max-w-3xl">
        <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-[#64748B]">
          INSA integrated platform
        </p>
        <h2
          id="platform-destinations-title"
          className="mt-2 text-2xl font-bold tracking-tight text-[#0A0D14] sm:text-3xl"
        >
          Explore connected project tools
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[#525866]">
          PROBE remains the central platform. These destinations open their existing
          applications separately; they do not share accounts or exchange live data.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <article className="flex h-full flex-col rounded-2xl border border-[#E5E7EB] bg-white p-5 sm:p-6">
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[#DBEAFE] bg-[#EFF6FF] text-[#0F52BA]">
              <CloudSun size={19} aria-hidden="true" />
            </span>
            <div>
              <h3 className="text-base font-semibold text-[#0A0D14]">
                Drought Intelligence
              </h3>
              <p className="mt-1 text-sm leading-relaxed text-[#525866]">
                The existing Admas AI site includes a dashboard, forecast interface,
                agricultural chatbot, and policy information, with English, Amharic,
                and Oromo language options.
              </p>
            </div>
          </div>
          <p className="mt-4 rounded-lg bg-[#F8FAFC] px-3 py-2 text-xs leading-relaxed text-[#475467]">
            The dashboard figures and forecast results are simulated in the current
            frontend; they are not validated live drought predictions.
          </p>
          <a
            href={platformDestinations.drought}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-5 inline-flex min-h-10 w-fit items-center gap-2 rounded-xl bg-[#0A0D14] px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#202530] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0F52BA] focus-visible:ring-offset-2"
          >
            Open Drought Intelligence
            <ArrowUpRight size={15} aria-hidden="true" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        </article>

        <article className="flex h-full flex-col rounded-2xl border border-[#E5E7EB] bg-white p-5 sm:p-6">
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[#D1FAE5] bg-[#ECFDF5] text-[#047857]">
              <MapPinned size={19} aria-hidden="true" />
            </span>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-base font-semibold text-[#0A0D14]">PNIS</h3>
                <span className="rounded-full border border-[#FDE68A] bg-[#FFFBEB] px-2.5 py-1 text-[10px] font-semibold text-[#92400E]">
                  Preview — In Development
                </span>
              </div>
              <p className="mt-1 text-sm leading-relaxed text-[#525866]">
                The existing Streamlit dashboard explores Sidama crop-collection
                candidates, geospatial data, fieldwork records, and road-network
                readiness using available project files.
              </p>
            </div>
          </div>
          <p className="mt-4 rounded-lg bg-[#F8FAFC] px-3 py-2 text-xs leading-relaxed text-[#475467]">
            Data availability varies by source file. A calculated graph path does not
            establish road passability or authorize dispatch.
          </p>
          <a
            href={platformDestinations.pnis}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-5 inline-flex min-h-10 w-fit items-center gap-2 rounded-xl border border-[#CBD5E1] bg-white px-4 py-2 text-sm font-semibold text-[#0A0D14] transition-colors hover:bg-[#F8FAFC] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0F52BA] focus-visible:ring-offset-2"
          >
            Open PNIS preview
            <ArrowUpRight size={15} aria-hidden="true" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        </article>
      </div>
    </div>
  </section>
);

export default PlatformDestinationsSection;
