const _MAP: Record<string, string> = {
  // US airlines
  AAL: "American Airlines", UAL: "United Airlines", DAL: "Delta Air Lines",
  SWA: "Southwest", JBU: "JetBlue", ASA: "Alaska Airlines",
  NKS: "Spirit", FFT: "Frontier", SKW: "SkyWest", RPA: "Republic Airways",
  ENY: "Envoy Air", AWI: "Air Wisconsin", JIA: "PSA Airlines",
  PDT: "Piedmont Airlines", CPZ: "Compass Airlines", GJS: "GoJet",
  EDV: "Endeavor Air", MES: "Mesa Airlines", HAL: "Hawaiian Airlines",
  AAY: "Allegiant Air", SCX: "Sun Country", BXR: "Breeze Airways",
  // US cargo
  FDX: "FedEx", UPS: "UPS", GTI: "Atlas Air", ABX: "ABX Air",
  // International airlines
  BAW: "British Airways", DLH: "Lufthansa", AFR: "Air France",
  KLM: "KLM", EZY: "easyJet", RYR: "Ryanair", UAE: "Emirates",
  QTR: "Qatar Airways", SIA: "Singapore Airlines", ANA: "ANA",
  JAL: "JAL", CPA: "Cathay Pacific", QFA: "Qantas", THY: "Turkish Airlines",
  TAP: "TAP Portugal", IBE: "Iberia", ACA: "Air Canada",
  WJA: "WestJet", AZA: "ITA Airways", CSN: "China Southern",
  CCA: "Air China", CES: "China Eastern", EVA: "EVA Air",
  CAL: "China Airlines", KAL: "Korean Air", AAR: "Asiana",
  SAS: "SAS", FIN: "Finnair", LOT: "LOT Polish", ICE: "Icelandair",
  EIN: "Aer Lingus", VIR: "Virgin Atlantic", AZU: "Azul",
  LAN: "LATAM", AVA: "Avianca", CMP: "Copa Airlines",
  VOI: "Volaris", AMX: "Aeromexico",
  // US military
  BOMR: "USAF Bomber", RNGR: "US Army Ranger", MNTNA: "Montana ANG",
  RCH: "USAF AMC (Reach)", EVAC: "USAF Aeromedical",
  DUKE: "USAF (Duke)", TOPCAT: "USN (Topcat)",
  VIPER: "USAF Fighter", EAGLE: "USAF Fighter",
  HAVOC: "US Army Attack", DUSTOFF: "US Army Medevac",
  PEDRO: "USAF Rescue", JOLLY: "USAF Rescue",
  PAT: "USAF VIP (Patriot)", SAM: "USAF Special Air Mission",
  EXEC: "USAF Executive", SPAR: "USAF Special Priority",
  AEVAC: "USAF Aeromedical", GONKY: "USAF Tanker",
  TEAL: "USAF (Teal)", DOOM: "USAF (Doom)",
  CNV: "US Navy", NAVY: "US Navy",
  CFC: "USAF Cadet", IRON: "USAF (Iron)",
  TOPGUN: "USN (Topgun)", BLADE: "US Army Helicopter",
  HAWK: "Military (Hawk)", COBRA: "Military (Cobra)",
  TITAN: "USAF (Titan)", GHOST: "Military (Ghost)",
  // Coast Guard / government
  CGD: "US Coast Guard", USCG: "US Coast Guard",
  CBP: "US Customs & Border", BRDSR: "US Border Patrol",
  // Other military
  ASCOT: "RAF (UK)", RAFR: "RAF (UK)", CANUK: "RCAF (Canada)",
  CANFORCE: "RCAF (Canada)", GAF: "German Air Force",
  FAF: "French Air Force", IAM: "Italian Air Force",
};

export function callsignLookup(callsign: string): string | null {
  const cs = callsign.trim().toUpperCase();
  if (!cs) return null;

  for (const len of [6, 5, 4, 3]) {
    const prefix = cs.slice(0, len);
    if (_MAP[prefix]) return _MAP[prefix];
  }

  if (cs.startsWith("N") && /^N\d/.test(cs)) return "Private (US)";
  if (cs.startsWith("C-") || cs.startsWith("CF-")) return "Private (Canada)";
  if (cs.startsWith("G-")) return "Private (UK)";

  return null;
}
