/// Strict projection of the current backend `GET /api/v1/mobile/me` contract.
///
/// Fields (verified against `origin/main` `MobileCitizenProfileRead`):
///   citizen_reference, display_name, phone, registered_address,
///   national_id_masked, identity_status
///
/// The donor branch parsed the stale `national_id_last4` / root `data_reality`
/// shape — that is repaired here (Codex P0-01 / H2). `registered_address` is
/// account context only; it is never used as an emergency location.
class CitizenProfile {
  const CitizenProfile({
    required this.citizenReference,
    required this.displayName,
    required this.phone,
    required this.registeredAddress,
    required this.nationalIdMasked,
    required this.identityStatus,
  });

  final String citizenReference;
  final String displayName;
  final String phone;
  final String registeredAddress;
  final String nationalIdMasked;
  final String identityStatus;

  String get initials {
    final parts = displayName
        .trim()
        .split(RegExp(r'\s+'))
        .where((p) => p.isNotEmpty)
        .toList();
    if (parts.isEmpty) return 'SG';
    String head(String s) =>
        s.runes.isEmpty ? '' : String.fromCharCode(s.runes.first).toUpperCase();
    if (parts.length == 1) {
      final r = parts.first.runes.take(2).toList();
      return String.fromCharCodes(r).toUpperCase();
    }
    return '${head(parts.first)}${head(parts.last)}';
  }

  factory CitizenProfile.fromJson(Map<String, dynamic> json) {
    String req(String key) {
      final v = json[key];
      if (v is! String || v.isEmpty) {
        throw FormatException(
          'Contract mismatch: /mobile/me is missing "$key". Expected '
          'citizen_reference, display_name, phone, registered_address, '
          'national_id_masked, identity_status.',
        );
      }
      return v;
    }

    return CitizenProfile(
      citizenReference: req('citizen_reference'),
      displayName: req('display_name'),
      phone: req('phone'),
      registeredAddress: req('registered_address'),
      nationalIdMasked: req('national_id_masked'),
      identityStatus: req('identity_status'),
    );
  }
}
