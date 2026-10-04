import { clone, get, normalizeAccommodation } from "./helpers.js";

export function createWorkspace(context) {
  const {meta, state} = context;
  const runtime = new Map();
  const textBefore = new Map();
  const current = () => state.profiles.find((p) => p.id === state.activeId);
  const session = (p) => {
    if (!runtime.has(p.id))
      runtime.set(p.id, { errors: [], validated: null, artifact: null, page: 0 });
    return runtime.get(p.id);
  };
  function makeProfile(name, data, marks = {}) {
    data = normalizeAccommodation(clone(data));
    const sectionAnswers = {};
    for (const g of meta.groups.filter((g) => g.optional)) {
      sectionAnswers[g.path] = get(data, g.path) != null;
    }
    return {
      id: crypto.randomUUID(),
      name,
      data,
      marks: clone(marks),
      original: clone(data),
      confirmed: {},
      sectionAnswers,
      step: 0,
      view: "form",
      jsonText: JSON.stringify(data, null, 2),
      jsonDirty: false,
      revision: 0,
      updated: Date.now(),
      signature: null,
    };
  }
  function blankData() {
    return {
      personal: { other_nationalities: [] },
      passport: {},
      contact: {},
      residence: { lives_outside_country_of_nationality: null },
      occupation: {},
      journey: { purposes: [], main_destination: [] },
      previous_biometrics: { fingerprints_taken: null },
      accommodation: null,
      expenses: { applicant_means: [], sponsor_means: [] },
      application: { signature: { enabled: false, image_path: null } },
      guardian: null,
      eu_family_member: null,
      eu_family_exemption: null,
      inviting_company: null,
      final_destination_permit: null,
    };
  }

  return { runtime, textBefore, current, session, makeProfile, blankData };
}
