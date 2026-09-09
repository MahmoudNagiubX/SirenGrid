import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../core/localization/locale_cubit.dart';
import '../../core/localization/siren_localizations.dart';
import '../../core/services.dart';
import '../../core/theme.dart';
import '../auth/auth_cubit.dart';
import 'emergency_service.dart';
import 'widgets/confirmation_sheet.dart';
import 'widgets/emergency_service_card.dart';

// ponytail: truthful location readiness states without fake live-GPS claims
enum LocationReadinessState {
  checking,
  ready,
  unavailable,
  permissionRequired,
}

// ponytail: single consolidated HomeScreen matching canonical locked prototype
class HomeScreen extends StatefulWidget {
  final ValueChanged<EmergencyService>? onEmergencyConfirmed;
  final ValueChanged<String>? onEmergencySubmitted;

  const HomeScreen({
    super.key,
    this.onEmergencyConfirmed,
    this.onEmergencySubmitted,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  LocationReadinessState _locationState = LocationReadinessState.checking;
  EmergencyService? _selectedService;

  EmergencyService? get selectedService => _selectedService;
  LocationReadinessState get locationState => _locationState;

  @override
  void initState() {
    super.initState();
    _initLocationReadiness();
  }

  Future<void> _initLocationReadiness() async {
    final result = await LocationService.checkReadiness();
    if (mounted) {
      setState(() {
        switch (result) {
          case LocationReadinessResult.ready:
            _locationState = LocationReadinessState.ready;
            break;
          case LocationReadinessResult.permissionRequired:
          case LocationReadinessResult.permissionDeniedForever:
            _locationState = LocationReadinessState.permissionRequired;
            break;
          case LocationReadinessResult.disabled:
          case LocationReadinessResult.unavailable:
            _locationState = LocationReadinessState.unavailable;
            break;
        }
      });
    }
  }

  @visibleForTesting
  void setLocationState(LocationReadinessState state) {
    setState(() {
      _locationState = state;
    });
  }

  void _handleServiceTapped(EmergencyService service) {
    setState(() {
      _selectedService = service;
    });

    ConfirmationSheet.show(
      context: context,
      service: service,
      onConfirm: widget.onEmergencyConfirmed,
      onSubmitted: widget.onEmergencySubmitted,
    );
  }

  String _getInitials(String displayName, bool isArabic) {
    final clean = displayName.trim();
    if (clean.isEmpty) return isArabic ? 'م' : 'C';
    final parts = clean.split(RegExp(r'\s+'));
    if (parts.length >= 2) {
      final first = parts[0].isNotEmpty ? parts[0][0] : '';
      final second = parts[1].isNotEmpty ? parts[1][0] : '';
      return '$first.$second';
    }
    return clean.isNotEmpty ? clean[0] : (isArabic ? 'م' : 'C');
  }

  @override
  Widget build(BuildContext context) {
    final authState = context.watch<AuthCubit>().state;
    final profile = authState.profile;
    final isArabic = context.watch<LocaleCubit>().isArabic;

    final displayName = profile?.displayName.isNotEmpty == true
        ? profile!.displayName
        : (isArabic ? 'مواطن' : 'Citizen');
    final initials = _getInitials(displayName, isArabic);
    final colors = context.colors;

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // User Profile Greeting Section (Authoritative data from CitizenProfile)
              Row(
                children: [
                  Container(
                    width: 48,
                    height: 48,
                    decoration: const BoxDecoration(
                      color: AppColors.avatarNavy,
                      shape: BoxShape.circle,
                    ),
                    child: Center(
                      child: Text(
                        initials,
                        style: const TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: Colors.white,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${context.tr('home.greeting_prefix')} $displayName',
                          style: TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.w700,
                            color: colors.textPrimary,
                            height: 1.2,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 2),
                        Text(
                          context.tr('home.greeting_sub'),
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w400,
                            color: colors.textMuted,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),

              // Location Readiness Area (Truthful representation: no fake coordinates)
              Container(
                key: const Key('home_location_readiness_card'),
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: colors.surface,
                  borderRadius: BorderRadius.circular(AppRadii.card),
                  border: Border.all(color: colors.border),
                ),
                child: Row(
                  children: [
                    Icon(
                      _locationState == LocationReadinessState.ready
                          ? Icons.my_location
                          : _locationState == LocationReadinessState.checking
                              ? Icons.location_searching
                              : Icons.location_off_outlined,
                      size: 24,
                      color: _locationState == LocationReadinessState.ready
                          ? AppColors.statusVerifiedText
                          : _locationState == LocationReadinessState.permissionRequired || _locationState == LocationReadinessState.unavailable
                              ? const Color(0xFFDC2626)
                              : AppColors.accentBlue,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            _locationState == LocationReadinessState.ready
                                ? context.tr('home.location_verified')
                                : _locationState == LocationReadinessState.permissionRequired
                                    ? (isArabic ? 'إذن الموقع مطلوب' : 'Location Permission Required')
                                    : _locationState == LocationReadinessState.unavailable
                                        ? (isArabic ? 'خدمات الموقع معطلة' : 'Location Services Disabled')
                                        : isArabic
                                            ? 'فحص جاهزية الموقع'
                                            : 'Location Readiness Check',
                            style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                              color: colors.textPrimary,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            _locationState == LocationReadinessState.ready
                                ? 'GPS Ready'
                                : _locationState == LocationReadinessState.permissionRequired
                                    ? (isArabic ? 'يرجى منح إذن الموقع لتحديد مكان الطوارئ' : 'Please grant location access to pinpoint emergency')
                                    : _locationState == LocationReadinessState.unavailable
                                        ? (isArabic ? 'يرجى تفعيل الـ GPS في إعدادات جهازك' : 'Please enable GPS in device settings')
                                        : isArabic
                                            ? 'سيتم تحديد موقعك بدقة عند إرسال البلاغ'
                                            : 'GPS coordinates acquired upon emergency submission',
                            style: TextStyle(
                              fontSize: 11,
                              color: colors.textMuted,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 20),

              // Emergency Section Header
              Text(
                context.tr('home.request_section'),
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.5,
                  color: colors.textSubtle,
                ),
              ),
              const SizedBox(height: 12),

              // 2x2 Emergency Services Grid (Responsive Row-Column Layout)
              Column(
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: EmergencyServiceCard(
                          service: EmergencyService.all[0], // Ambulance
                          onTap: () => _handleServiceTapped(EmergencyService.all[0]),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: EmergencyServiceCard(
                          service: EmergencyService.all[1], // Fire
                          onTap: () => _handleServiceTapped(EmergencyService.all[1]),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: EmergencyServiceCard(
                          service: EmergencyService.all[2], // Police
                          onTap: () => _handleServiceTapped(EmergencyService.all[2]),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: EmergencyServiceCard(
                          service: EmergencyService.all[3], // General Emergency
                          onTap: () => _handleServiceTapped(EmergencyService.all[3]),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 20),

              // Quick Dial 122 Action Card
              Container(
                key: const Key('home_hotline_banner'),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                decoration: BoxDecoration(
                  color: colors.surface,
                  borderRadius: BorderRadius.circular(AppRadii.card),
                  border: Border.all(color: colors.border),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        color: colors.neutralCard,
                        shape: BoxShape.circle,
                      ),
                      child: Center(
                        child: Icon(
                          Icons.phone_outlined,
                          size: 18,
                          color: colors.textMuted,
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            context.tr('home.quick_dial_title'),
                            style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                              color: colors.textPrimary,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            context.tr('home.quick_dial_sub'),
                            style: TextStyle(
                              fontSize: 11,
                              color: colors.textMuted,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      decoration: BoxDecoration(
                        color: colors.accentBlueLight,
                        borderRadius: BorderRadius.circular(AppRadii.pill),
                        border: Border.all(color: const Color(0x262563EB)),
                      ),
                      child: Text(
                        context.tr('home.quick_dial_btn'),
                        style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: AppColors.accentBlue,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
