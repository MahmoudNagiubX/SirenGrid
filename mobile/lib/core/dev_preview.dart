import '../features/auth/auth_cubit.dart';
import '../features/tracking/tracking_cubit.dart';

/// Development-Only UI Preview Configuration and Static Entities
/// Provides isolated mock structures for manual UI inspection while backend is offline.
/// Strictly guarded by AppConfig.isPreviewAllowed — never used for production authentication.
class DevPreviewConfig {
  static const previewCitizenProfile = CitizenProfile(
    citizenReference: 'preview-citizen',
    displayName: 'Demo Citizen',
    phone: '+20 100 000 0000',
    maskedNationalId: '•••• •••• •••• 0000',
    status: 'Verified',
    dataReality: 'SIMULATED',
  );

  static const previewTrackingData = TrackingData(
    requestId: 'PREVIEW-REQ-001',
    incidentId: 'PREVIEW-INC-101',
    status: CitizenRequestStatus.enRoute,
    rawStatus: 'EN_ROUTE',
    service: 'AMBULANCE',
    etaSeconds: 240, // 4 minutes
    responder: ResponderData(
      label: 'Ambulance 14',
      location: ResponderLocation(lat: 30.0620, lon: 31.3380),
      dataReality: 'SIMULATED',
    ),
    dataReality: 'SIMULATED',
  );
}
