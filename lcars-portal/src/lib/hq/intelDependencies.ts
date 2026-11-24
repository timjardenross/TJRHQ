// Intelligence capabilities that depend on work still in other open pull
// requests (#711 provider-disruption / systemic / forward-watch products,
// #712 source coverage in the Intelligence workbench, #713 incident
// clustering and delivery tiers). HQ does NOT reimplement any of them. This
// list is the single place the dependency is recorded: when a capability
// merges, wire its existing API here and flip `connected`.
export interface IntelDependency {
  key: string;
  label: string;
  pr: string;
  connected: boolean;
}

export const INTEL_DEPENDENCIES: IntelDependency[] = [
  { key: 'incidents', label: 'Incident clustering and delivery tiers', pr: '#713', connected: false },
  { key: 'systemic', label: 'Provider disruption, systemic view and forward watch', pr: '#711', connected: false },
  { key: 'coverage', label: 'Source coverage', pr: '#712', connected: false },
];

export const pendingIntelDependencies = () => INTEL_DEPENDENCIES.filter((d) => !d.connected);
