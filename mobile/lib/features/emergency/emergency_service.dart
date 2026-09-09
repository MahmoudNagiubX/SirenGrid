/// The four citizen-selectable services. The backend enum is frozen to exactly
/// `AMBULANCE | FIRE | POLICE | GENERAL` (Master Plan §14.1); this is the single
/// source of truth for the UI ↔ API mapping. No police-fleet optimisation is
/// implied — Police/General are operator-review only on the backend.
enum EmergencyService {
  ambulance('AMBULANCE', 'ambulance', 'home.svc_ambulance'),
  fire('FIRE', 'flame', 'home.svc_fire'),
  police('POLICE', 'shield', 'home.svc_police'),
  general('GENERAL', 'siren', 'home.svc_general');

  const EmergencyService(this.apiCode, this.icon, this.labelKey);

  /// Value sent as `service` in `POST /mobile/emergency-requests`.
  final String apiCode;

  /// Lucide glyph name.
  final String icon;

  /// Localization key for the human label.
  final String labelKey;

  static EmergencyService fromApiCode(String code) {
    final upper = code.trim().toUpperCase();
    return EmergencyService.values.firstWhere(
      (s) => s.apiCode == upper,
      orElse: () => EmergencyService.general,
    );
  }
}
