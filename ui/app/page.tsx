"use client";

import { useEffect, useState } from "react";

// Every request goes to THIS origin. The browser never learns the service's address and never
// holds its credential; the route handler under /api/agent forwards, having discarded whatever
// identity the client tried to assert.
const API = "/api/agent";

// Mirrors the service's seeded local personas. The picker is a DEV convenience: the server
// validates the selection against its own list, so a hand-crafted value cannot invent a persona.
// Switching persona is how you show entitlement-suppressed retrieval live: an analyst sees fewer
// documents than an approver, and the pack says so with a count rather than with silence.
const PERSONAS = ["analyst", "approver", "auditor", "other-tenant"];

const INSTRUMENTS = [
  "rfi",
  "exam_request_list",
  "s166_skilled_person",
  "thematic_review",
  "information_notice",
];

const REGIMES = [
  "supervisory-information-request",
  "skilled-person-review",
  "thematic-supervisory-review",
];

const JURISDICTIONS = ["SG", "HK"];

const TOPICS = [
  "governance",
  "aml_financial_crime",
  "conduct_and_complaints",
  "credit_risk",
  "operational_resilience",
  "data_privacy",
  "model_risk",
  "outsourcing_third_party",
  "capital_and_liquidity",
  "technology_and_cyber",
];

const ARTEFACTS = [
  "policy",
  "procedure",
  "committee_minutes",
  "org_and_roles",
  "control_test_result",
  "risk_assessment",
  "issue_log",
  "third_party_contract",
  "system_extract",
  "transaction_sample",
  "customer_file",
  "management_information",
  "narrative_statement",
];

// How the due date was decided, spelled out. A basis nobody can read is a number nobody can
// challenge, and the whole point of recording the rule is that a person can argue with it.
const DUE_BASIS_WORDS: Record<string, string> = {
  regulator_stated: "the date the supervisor stated in the notice",
};

function dueBasisInWords(basis: string): string {
  if (DUE_BASIS_WORDS[basis]) return DUE_BASIS_WORDS[basis];
  if (basis.startsWith("policy_window:"))
    return "your configured response window for a " + basis.split(":")[1] + ", the notice stated no date";
  if (basis.startsWith("extension:"))
    return "a recorded extension, reference " + basis.split(":")[1];
  if (basis.startsWith("regime_cap:"))
    return "a fixed window the named regime " + basis.split(":")[1] + " sets";
  return basis;
}

interface CardSummary {
  name?: string;
  description?: string;
}

interface Citation {
  source_id: string;
  title: string;
  snippet?: string;
}

interface Sla {
  due_on: string;
  original_due_on?: string | null;
  due_basis: string;
  internal_due_on: string;
  extension_request_by: string;
  business_days_remaining: number;
  band: string;
  breached: boolean;
  buffer_consumed: boolean;
  calendar_id: string;
  calendar_version: string;
}

interface Coverage {
  artefact: string;
  state: string;
  mandatory: boolean;
  reason: string;
}

interface BlockerRow {
  kind: string;
  severity: string;
  detail: string;
  requirement_id?: string;
  citation: Citation;
}

interface ExhibitRow {
  exhibit_no: string;
  index_no?: string;
  doc_id: string;
  title: string;
  artefact: string;
  as_of: string;
  locator?: string;
  origin?: string;
}

interface WithholdRow {
  doc_id: string;
  title?: string;
  artefact: string;
  status: string;
  basis_rule: string;
  stated_basis: string;
}

interface Narrative {
  text?: string;
  drafted: boolean;
  model_authored: boolean;
  grounded: boolean;
  discard_reason?: string;
  proposed_artefacts?: string[];
}

interface ItemAnswer {
  item_ref: string;
  topic: string;
  owner?: string;
  disposition: string;
  severity: string;
  requires_human_review: boolean;
  review_ref?: string;
  completeness_pct: number;
  satisfied_mandatory: number;
  total_mandatory: number;
  out_of_scope_dropped: number;
  suppressed_by_entitlement: number;
  release_state: string;
  release_blockers: string[];
  required_approvals: number;
  sla: Sla;
  coverage: Coverage[];
  blockers: BlockerRow[];
  exhibits: ExhibitRow[];
  withheld: WithholdRow[];
  narrative: Narrative;
}

interface PackAnswer {
  request_id: string;
  reference: string;
  disposition: string;
  severity: string;
  summary: string;
  requires_human_review: boolean;
  review_ref?: string;
  release_state: string;
  release_blockers: string[];
  required_approvals: number;
  completeness_pct: number;
  as_of: string;
  sla: Sla;
  items: ItemAnswer[];
  document_index: ExhibitRow[];
  withholding_schedule: WithholdRow[];
  blockers: BlockerRow[];
  cover_note: Narrative;
}

interface DraftItem {
  item_ref: string;
  question: string;
  topic: string;
  requested_artefacts: string[];
  owner: string;
  item_due_on: string;
  evidence_pack_ref: string;
}

// Obviously fictional seed data, so a demo is one click. No real institution, person or
// identifier appears anywhere in this file.
const SEED_ITEMS: DraftItem[] = [
  {
    item_ref: "1.a",
    question:
      "Provide the financial-crime policy in force during the review period and the transaction-monitoring management information reported to the board for the two quarters ending in the period.",
    topic: "aml_financial_crime",
    requested_artefacts: ["policy", "management_information"],
    owner: "Head of Financial Crime (FICTIONAL)",
    item_due_on: "",
    evidence_pack_ref: "",
  },
  {
    item_ref: "3.a",
    question:
      "Provide all internal correspondence and legal analysis concerning the payments outage in the review period, together with the customer files of every affected client.",
    topic: "data_privacy",
    requested_artefacts: ["issue_log", "customer_file"],
    owner: "Data Protection Officer (FICTIONAL)",
    item_due_on: "",
    evidence_pack_ref: "",
  },
];

function emptyItem(index: number): DraftItem {
  return {
    item_ref: String(index),
    question: "",
    topic: TOPICS[0],
    requested_artefacts: [],
    owner: "",
    item_due_on: "",
    evidence_pack_ref: "",
  };
}

export default function Home() {
  const [persona, setPersona] = useState(PERSONAS[1]);
  const [card, setCard] = useState<CardSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState("");
  const [pack, setPack] = useState<PackAnswer | null>(null);
  const [open, setOpen] = useState<string>("");

  const [requestId, setRequestId] = useState("EXAM-2027-0014");
  const [regulator, setRegulator] = useState("Meridian Prudential Authority (FICTIONAL)");
  const [reference, setReference] = useState("MPA-FICTIONAL/EX/2027/0014");
  const [instrument, setInstrument] = useState(INSTRUMENTS[0]);
  const [regime, setRegime] = useState(REGIMES[0]);
  const [jurisdiction, setJurisdiction] = useState(JURISDICTIONS[0]);
  const [receivedOn, setReceivedOn] = useState("2027-03-01");
  const [regulatorDueOn, setRegulatorDueOn] = useState("2027-04-30");
  const [periodStart, setPeriodStart] = useState("2026-04-01");
  const [periodEnd, setPeriodEnd] = useState("2027-02-28");
  const [asOf, setAsOf] = useState("2027-03-15");
  const [extensionRef, setExtensionRef] = useState("");
  const [waiverRef, setWaiverRef] = useState("");
  const [items, setItems] = useState<DraftItem[]>(SEED_ITEMS);

  // The service names itself, so this UI carries no hardcoded product name to go stale.
  useEffect(() => {
    let live = true;
    fetch(API + "/.well-known/agent-card.json", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (live) setCard(body as CardSummary | null);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  function patchItem(index: number, patch: Partial<DraftItem>) {
    setItems((current) =>
      current.map((item, position) => (position === index ? { ...item, ...patch } : item)),
    );
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailed("");
    try {
      const response = await fetch(API + "/v1/response-pack", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Dev-Persona": persona },
        body: JSON.stringify({
          request_id: requestId,
          regulator,
          reference,
          instrument,
          regime,
          jurisdiction,
          received_on: receivedOn,
          period_start: periodStart,
          period_end: periodEnd,
          regulator_due_on: regulatorDueOn || null,
          as_of: asOf || null,
          extension_ref: extensionRef,
          waiver_ref: waiverRef,
          items: items.map((item) => ({
            item_ref: item.item_ref,
            question: item.question,
            topic: item.topic,
            requested_artefacts: item.requested_artefacts,
            owner: item.owner,
            item_due_on: item.item_due_on || null,
            evidence_pack_ref: item.evidence_pack_ref,
          })),
        }),
      });
      const body = await response.text();
      if (!response.ok) {
        setPack(null);
        setFailed(body);
        return;
      }
      setPack(JSON.parse(body) as PackAnswer);
    } catch (error) {
      setPack(null);
      setFailed(String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>{card?.name ?? "Exam response console"}</h1>
      <p className="sub">
        {card?.description ??
          "Turn a supervisor's numbered questions into a citation-backed, deadline-tracked response pack. Nothing here releases anything."}
      </p>

      <form onSubmit={submit}>
        <fieldset>
          <legend>Who you are</legend>
          <label>
            Seeded dev persona, local profile only; the server resolves identity and its
            entitlements, not this field
            <select value={persona} onChange={(event) => setPersona(event.target.value)}>
              {PERSONAS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </fieldset>

        <fieldset>
          <legend>The instrument</legend>
          <label>
            Firm case id
            <input value={requestId} onChange={(event) => setRequestId(event.target.value)} />
          </label>
          <label>
            Supervisor
            <input value={regulator} onChange={(event) => setRegulator(event.target.value)} />
          </label>
          <label>
            Supervisor reference
            <input value={reference} onChange={(event) => setReference(event.target.value)} />
          </label>
          <label>
            Instrument
            <select value={instrument} onChange={(event) => setInstrument(event.target.value)}>
              {INSTRUMENTS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Named regime
            <select value={regime} onChange={(event) => setRegime(event.target.value)}>
              {REGIMES.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Jurisdiction (selects the business calendar and the transfer scope)
            <select
              value={jurisdiction}
              onChange={(event) => setJurisdiction(event.target.value)}
            >
              {JURISDICTIONS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Received on
            <input value={receivedOn} onChange={(event) => setReceivedOn(event.target.value)} />
          </label>
          <label>
            Regulator due on (leave blank when the letter stated none)
            <input
              value={regulatorDueOn}
              onChange={(event) => setRegulatorDueOn(event.target.value)}
            />
          </label>
          <label>
            Review period start
            <input value={periodStart} onChange={(event) => setPeriodStart(event.target.value)} />
          </label>
          <label>
            Review period end
            <input value={periodEnd} onChange={(event) => setPeriodEnd(event.target.value)} />
          </label>
          <label>
            Evaluate as of (optional; blank lets the server resolve and echo the date)
            <input value={asOf} onChange={(event) => setAsOf(event.target.value)} />
          </label>
          <label>
            Extension REFERENCE (a lookup key into the case store; it grants nothing)
            <input
              value={extensionRef}
              onChange={(event) => setExtensionRef(event.target.value)}
            />
          </label>
          <label>
            Privilege waiver REFERENCE (a lookup key into the case store; it grants nothing)
            <input value={waiverRef} onChange={(event) => setWaiverRef(event.target.value)} />
          </label>
        </fieldset>

        <fieldset>
          <legend>The questions</legend>
          {items.map((item, index) => (
            <div key={index} className="itemRow">
              <label>
                Item reference
                <input
                  value={item.item_ref}
                  onChange={(event) => patchItem(index, { item_ref: event.target.value })}
                />
              </label>
              <label>
                Question as written
                <textarea
                  value={item.question}
                  onChange={(event) => patchItem(index, { question: event.target.value })}
                />
              </label>
              <label>
                Topic
                <select
                  value={item.topic}
                  onChange={(event) => patchItem(index, { topic: event.target.value })}
                >
                  {TOPICS.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Artefacts the supervisor named
                <select
                  multiple
                  value={item.requested_artefacts}
                  onChange={(event) =>
                    patchItem(index, {
                      requested_artefacts: Array.from(
                        event.target.selectedOptions,
                        (option) => option.value,
                      ),
                    })
                  }
                >
                  {ARTEFACTS.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Owner (blank is unassigned, which is a blocker rather than a default)
                <input
                  value={item.owner}
                  onChange={(event) => patchItem(index, { owner: event.target.value })}
                />
              </label>
              <label>
                Item due on (optional)
                <input
                  value={item.item_due_on}
                  onChange={(event) => patchItem(index, { item_due_on: event.target.value })}
                />
              </label>
              <label>
                Evidence pack reference (optional)
                <input
                  value={item.evidence_pack_ref}
                  onChange={(event) =>
                    patchItem(index, { evidence_pack_ref: event.target.value })
                  }
                />
              </label>
            </div>
          ))}
          <button
            type="button"
            className="ghost"
            onClick={() => setItems((current) => [...current, emptyItem(current.length + 1)])}
          >
            Add a question
          </button>
          <button type="submit" disabled={busy}>
            {busy ? "Working" : "Assemble the response pack"}
          </button>
        </fieldset>
      </form>

      {failed ? <pre className="result error">{failed}</pre> : null}

      {pack ? (
        <section>
          <div className={"banner " + pack.disposition}>
            <strong>{pack.disposition.replace("_", " ").toUpperCase()}</strong>
            <span className="sub">
              {pack.reference} evaluated as of {pack.as_of}; completeness{" "}
              {pack.completeness_pct} per cent
            </span>
          </div>

          <div className="clock">
            <span>Due {pack.sla.due_on}</span>
            <span>Because: {dueBasisInWords(pack.sla.due_basis)}</span>
            <span>Internal due {pack.sla.internal_due_on}</span>
            <span>{pack.sla.business_days_remaining} business days remaining</span>
            <span className={"chip " + pack.sla.band}>band {pack.sla.band}</span>
            <span>Ask for an extension by {pack.sla.extension_request_by}</span>
            {pack.sla.original_due_on ? (
              <span>Before the extension: {pack.sla.original_due_on}</span>
            ) : null}
            <small>
              Calendar {pack.sla.calendar_id} version {pack.sla.calendar_version}. A deadline
              nobody can trace to a calendar is not evidence.
            </small>
          </div>

          <h2>Blockers</h2>
          {pack.blockers.length === 0 ? (
            <p className="sub">Nothing is blocking this pack.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Rule</th>
                  <th>Severity</th>
                  <th>Detail</th>
                  <th>Citation</th>
                </tr>
              </thead>
              <tbody>
                {pack.blockers.map((blocker, index) => (
                  <tr key={index}>
                    <td>{blocker.kind}</td>
                    <td>{blocker.severity}</td>
                    <td>{blocker.detail}</td>
                    <td>{blocker.citation?.title || blocker.citation?.source_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2>Items</h2>
          <table>
            <thead>
              <tr>
                <th>Item</th>
                <th>Topic</th>
                <th>Disposition</th>
                <th>Completeness</th>
                <th>Owner</th>
                <th>Exhibits</th>
                <th>Blockers</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {pack.items.map((item) => (
                <tr key={item.item_ref}>
                  <td>{item.item_ref}</td>
                  <td>{item.topic}</td>
                  <td>{item.disposition}</td>
                  <td>
                    {item.satisfied_mandatory} of {item.total_mandatory} ({item.completeness_pct}
                    %)
                  </td>
                  <td>{item.owner || "UNASSIGNED"}</td>
                  <td>{item.exhibits.length}</td>
                  <td>{item.blockers.length}</td>
                  <td>
                    <button
                      type="button"
                      className="ghost"
                      onClick={() => setOpen(open === item.item_ref ? "" : item.item_ref)}
                    >
                      {open === item.item_ref ? "Hide coverage" : "Open coverage"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {pack.items
            .filter((item) => item.item_ref === open)
            .map((item) => (
              <table key={item.item_ref}>
                <thead>
                  <tr>
                    <th>Artefact</th>
                    <th>State</th>
                    <th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  {item.coverage.map((row) => (
                    <tr key={row.artefact} className={"cov " + row.state}>
                      <td>{row.artefact}</td>
                      <td>{row.state}</td>
                      <td>{row.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ))}

          <h2>Withholding schedule</h2>
          {pack.withholding_schedule.length === 0 ? (
            <p className="sub">Nothing was withheld.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Status</th>
                  <th>Rule</th>
                  <th>Stated basis</th>
                </tr>
              </thead>
              <tbody>
                {pack.withholding_schedule.map((row) => (
                  <tr key={row.doc_id} className={"wh " + row.status}>
                    <td>
                      {row.doc_id}
                      {row.title ? " " + row.title : " (title withheld)"}
                    </td>
                    <td>{row.status}</td>
                    <td>{row.basis_rule}</td>
                    <td>{row.stated_basis}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="sub">
            Withheld, denied and missing are different statements and are shown differently.
            Withheld means the firm holds it and is not producing it, with a basis. Denied means
            this caller may not read it. Missing means the firm produced no such document.
          </p>

          <h2>Document index</h2>
          {pack.document_index.length === 0 ? (
            <p className="sub">No admissible evidence was retrieved, so nothing is indexed.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Index</th>
                  <th>Exhibit</th>
                  <th>Title</th>
                  <th>Class</th>
                  <th>As of</th>
                  <th>Locator</th>
                </tr>
              </thead>
              <tbody>
                {pack.document_index.map((row) => (
                  <tr key={row.index_no || row.exhibit_no}>
                    <td>{row.index_no}</td>
                    <td>{row.exhibit_no}</td>
                    <td>{row.title}</td>
                    <td>{row.artefact}</td>
                    <td>{row.as_of}</td>
                    <td>{row.locator}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2>Release</h2>
          <table>
            <tbody>
              <tr>
                <td>Release state</td>
                <td>{pack.release_state}</td>
              </tr>
              <tr>
                <td>Required approvals</td>
                <td>{pack.required_approvals}</td>
              </tr>
              <tr>
                <td>Review reference</td>
                <td>{pack.review_ref || "not routed"}</td>
              </tr>
              <tr>
                <td>Named release blockers</td>
                <td>{pack.release_blockers.join(", ") || "none"}</td>
              </tr>
            </tbody>
          </table>
          <p className="sub">
            This console cannot release anything. The approvals are recorded in the human-review
            console and an operator sends the production.
          </p>

          <h2>Cover note and drafts</h2>
          <Draft label="Cover note" draft={pack.cover_note} />
          {pack.items.map((item) => (
            <Draft key={item.item_ref} label={"Item " + item.item_ref} draft={item.narrative} />
          ))}
        </section>
      ) : null}

      <footer>
        The pack requires {pack ? pack.required_approvals : 2} approvals and carries its review
        reference before anything leaves the firm. The browser asserts no actor, tenant or
        entitlement: what may be retrieved was decided from the verified principal. All data is
        synthetic and fictional. See ui/README.md for the embedding contract.
      </footer>
    </main>
  );
}

function Draft({ label, draft }: { label: string; draft: Narrative }) {
  if (!draft.drafted) {
    return (
      <p className="placard">
        {label}: no admissible evidence was retrieved, so nothing was drafted.
        {draft.discard_reason ? " " + draft.discard_reason : ""}
      </p>
    );
  }
  return (
    <div className="draft">
      <span className={"chip " + (draft.model_authored ? "model" : "engine")}>
        {draft.model_authored ? "model-authored" : "deterministic fallback"}
      </span>
      <p>{draft.text}</p>
      {draft.discard_reason ? (
        <p className="sub">The model draft was discarded: {draft.discard_reason}</p>
      ) : null}
      {draft.proposed_artefacts && draft.proposed_artefacts.length > 0 ? (
        <p className="advisory">
          Suggested by the model and counting towards nothing: {draft.proposed_artefacts.join(", ")}
        </p>
      ) : null}
    </div>
  );
}
