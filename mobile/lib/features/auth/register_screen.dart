import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/location.dart';
import '../../design/components/sg_buttons.dart';
import '../../design/components/sg_forms.dart';
import '../../design/sg_icon.dart';
import '../../design/tokens.dart';
import '../../l10n/strings.dart';
import 'auth_cubit.dart';

typedef CaptureIdImage = Future<String?> Function();
typedef ScanIdImage = Future<Map<String, dynamic>> Function(String imagePath);
typedef DiscardIdImage = Future<void> Function(String imagePath);

enum IdScanState {
  idle,
  cameraCancelled,
  imageCaptured,
  uploading,
  scanning,
  success,
  partialResult,
  cardNotDetected,
  ocrNotClear,
  invalidNationalId,
  backendUnavailable,
  timeout,
}

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({
    super.key,
    this.locationService,
    this.captureIdImage,
    this.scanIdImage,
    this.discardIdImage,
  });

  final LocationService? locationService;
  final CaptureIdImage? captureIdImage;
  final ScanIdImage? scanIdImage;
  final DiscardIdImage? discardIdImage;

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

enum _LocState { idle, capturing, saved, failed }

class _RegisterScreenState extends State<RegisterScreen> {
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _nid = TextEditingController();
  final _pin = TextEditingController();
  final _pinConfirm = TextEditingController();
  final _address = TextEditingController();

  late final LocationService _location =
      widget.locationService ?? LocationService();

  IdScanState _scanState = IdScanState.idle;
  _LocState _locState = _LocState.idle;
  String? _imagePath;
  String? _scanMessage;
  List<String> _scanWarnings = const [];
  Map<String, String> _derived = const {};
  bool _showForm = false;
  double? _lat;
  double? _lon;

  String? _nameErr;
  String? _phoneErr;
  String? _nidErr;
  String? _pinErr;
  String? _pinConfirmErr;
  String? _addressErr;

  bool get _scanBusy =>
      _scanState == IdScanState.uploading || _scanState == IdScanState.scanning;

  bool get _scanFailed => {
    IdScanState.cameraCancelled,
    IdScanState.cardNotDetected,
    IdScanState.ocrNotClear,
    IdScanState.invalidNationalId,
    IdScanState.backendUnavailable,
    IdScanState.timeout,
  }.contains(_scanState);

  @override
  void dispose() {
    for (final controller in [
      _name,
      _phone,
      _nid,
      _pin,
      _pinConfirm,
      _address,
    ]) {
      controller.clear();
      controller.dispose();
    }
    unawaited(_discardCapturedImage());
    super.dispose();
  }

  String _digits(String value) => value.replaceAll(RegExp(r'\D'), '');

  bool _validNationalId(String value) {
    if (!RegExp(r'^[0-9]{14}$').hasMatch(value)) return false;
    final century = switch (value[0]) {
      '2' => 1900,
      '3' => 2000,
      _ => null,
    };
    if (century == null) return false;
    final year = century + int.parse(value.substring(1, 3));
    final month = int.parse(value.substring(3, 5));
    final day = int.parse(value.substring(5, 7));
    final date = DateTime.utc(year, month, day);
    return date.year == year && date.month == month && date.day == day;
  }

  Future<String?> _nativeCamera() async {
    final image = await ImagePicker().pickImage(
      source: ImageSource.camera,
      imageQuality: 92,
      preferredCameraDevice: CameraDevice.rear,
    );
    return image?.path;
  }

  Future<void> _discardCapturedImage() async {
    final path = _imagePath;
    _imagePath = null;
    if (path == null) return;
    final discard = widget.discardIdImage;
    if (discard != null) {
      await discard(path);
      return;
    }
    try {
      final image = File(path);
      if (await image.exists()) await image.delete();
    } catch (_) {
      // The OS may already have cleared its temporary camera file.
    }
  }

  Future<void> _startCapture() async {
    final openCamera = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => const _ScanInstructions(),
    );
    if (openCamera != true || !mounted) return;
    try {
      final path = await (widget.captureIdImage ?? _nativeCamera).call();
      if (!mounted) return;
      if (path == null) {
        setState(() {
          _scanState = IdScanState.cameraCancelled;
          _scanMessage = context.tr('register.scan_cancelled');
        });
        return;
      }
      setState(() {
        _imagePath = path;
        _scanState = IdScanState.imageCaptured;
        _scanMessage = null;
        _scanWarnings = const [];
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _scanState = IdScanState.cameraCancelled;
        _scanMessage = context.tr('register.camera_unavailable');
      });
    }
  }

  Future<void> _scanCapturedImage() async {
    final path = _imagePath;
    if (path == null || _scanBusy) return;
    setState(() {
      _scanState = IdScanState.uploading;
      _scanMessage = null;
    });
    final scan = widget.scanIdImage ?? context.read<AuthCubit>().scanNationalId;
    final pending = scan(path);
    await Future<void>.delayed(Duration.zero);
    if (mounted) setState(() => _scanState = IdScanState.scanning);
    final result = await pending;
    await _discardCapturedImage();
    if (!mounted) return;

    if (result['success'] == true && result['extracted'] is Map) {
      final extracted = Map<String, dynamic>.from(result['extracted'] as Map);
      _name.text = extracted['full_name']?.toString() ?? '';
      _nid.text = extracted['national_id']?.toString() ?? '';
      _address.text = extracted['registered_address_text']?.toString() ?? '';
      _derived = {
        for (final key in ['birth_date', 'governorate', 'gender'])
          if ((extracted[key]?.toString() ?? '').isNotEmpty)
            key: extracted[key].toString(),
      };
      _scanWarnings = (result['warnings'] as List? ?? const [])
          .map((value) => value.toString())
          .toList(growable: false);
      final partial =
          _scanWarnings.isNotEmpty ||
          _name.text.isEmpty ||
          _address.text.isEmpty;
      setState(() {
        _scanState = partial ? IdScanState.partialResult : IdScanState.success;
        _showForm = true;
        _scanMessage = null;
      });
      return;
    }

    final code = result['code']?.toString();
    setState(() {
      _scanState = switch (code) {
        'ID_CARD_NOT_DETECTED' => IdScanState.cardNotDetected,
        'INVALID_NATIONAL_ID' => IdScanState.invalidNationalId,
        'TIMEOUT' => IdScanState.timeout,
        'BACKEND_UNAVAILABLE' ||
        'OCR_UNAVAILABLE' => IdScanState.backendUnavailable,
        _ => IdScanState.ocrNotClear,
      };
      _scanMessage =
          result['message']?.toString() ?? context.tr('register.ocr_not_clear');
    });
  }

  Future<void> _retake() async {
    await _discardCapturedImage();
    if (!mounted) return;
    setState(() {
      _name.clear();
      _nid.clear();
      _address.clear();
      _derived = const {};
      _scanWarnings = const [];
      _scanState = IdScanState.idle;
      _showForm = false;
    });
    await _startCapture();
  }

  void _manualEntry() {
    unawaited(_discardCapturedImage());
    setState(() {
      _scanState = IdScanState.idle;
      _scanMessage = null;
      _scanWarnings = const [];
      _derived = const {};
      _showForm = true;
    });
  }

  bool _validate() {
    final name = _name.text.trim();
    final phone = _digits(_phone.text);
    final nid = _digits(_nid.text);
    final pin = _pin.text;
    final pinConfirm = _pinConfirm.text;
    final address = _address.text.trim();

    setState(() {
      _nameErr = name.isEmpty ? context.tr('register.err_name') : null;
      _phoneErr = RegExp(r'^01\d{9}$').hasMatch(phone)
          ? null
          : context.tr('register.err_phone');
      _nidErr = _validNationalId(nid) ? null : context.tr('register.err_nid');
      _pinErr = RegExp(r'^\d{4,8}$').hasMatch(pin)
          ? null
          : context.tr('register.err_pin');
      _pinConfirmErr = pin == pinConfirm
          ? null
          : context.tr('register.err_pin_mismatch');
      _addressErr = address.length < 3
          ? context.tr('register.err_address')
          : null;
    });
    return [
      _nameErr,
      _phoneErr,
      _nidErr,
      _pinErr,
      _pinConfirmErr,
      _addressErr,
    ].every((error) => error == null);
  }

  Future<void> _useCurrentLocation() async {
    setState(() => _locState = _LocState.capturing);
    try {
      final position = await _location.freshPosition();
      if (!mounted) return;
      setState(() {
        _lat = position.latitude;
        _lon = position.longitude;
        _locState = _LocState.saved;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _lat = null;
        _lon = null;
        _locState = _LocState.failed;
      });
    }
  }

  void _submit(bool busy) {
    if (busy) return;
    FocusScope.of(context).unfocus();
    if (!_validate()) return;
    context.read<AuthCubit>().register({
      'display_name': _name.text.trim(),
      'phone': _digits(_phone.text),
      'national_id': _digits(_nid.text),
      'pin': _pin.text,
      'pin_confirm': _pinConfirm.text,
      'registered_address_text': _address.text.trim(),
      if (_lat != null && _lon != null) ...{
        'registered_latitude': _lat,
        'registered_longitude': _lon,
      },
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: const Key('register_screen'),
      backgroundColor: SgColors.bgApp,
      body: SafeArea(
        child: BlocConsumer<AuthCubit, AuthState>(
          listenWhen: (_, state) => state is Authenticated,
          listener: (context, state) {
            if (state is Authenticated && Navigator.of(context).canPop()) {
              Navigator.of(context).pop();
            }
          },
          builder: (context, state) {
            final authBusy = state is AuthInProgress;
            final failure = state is AuthFailure && state.loginFailure
                ? state.message
                : null;
            final bannerError = failure == null
                ? null
                : (failure.contains('.') && !failure.contains(' ')
                      ? context.tr(failure)
                      : failure);
            return Column(
              children: [
                _TopBar(onBack: authBusy ? null : Navigator.of(context).pop),
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(26, 8, 26, 28),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          'SirenGrid',
                          style: SgType.captionMedium.copyWith(
                            color: SgColors.infoStrong,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          context.tr('register.title'),
                          style: SgType.title.copyWith(
                            color: SgColors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          context.tr('register.subtitle'),
                          style: SgType.caption.copyWith(
                            color: SgColors.textMuted,
                          ),
                        ),
                        const SizedBox(height: 22),
                        _buildScanSection(),
                        if (_showForm) ...[
                          const SizedBox(height: 24),
                          if (bannerError != null) ...[
                            _ErrorBanner(bannerError),
                            const SizedBox(height: 16),
                          ],
                          _buildRegistrationForm(authBusy),
                        ],
                      ],
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _buildScanSection() {
    if (_scanBusy) return const _ScanningCard();
    if (_scanState == IdScanState.imageCaptured && _imagePath != null) {
      return _ImagePreview(
        path: _imagePath!,
        onRetake: _retake,
        onUse: _scanCapturedImage,
      );
    }
    if (_scanState == IdScanState.success ||
        _scanState == IdScanState.partialResult) {
      return _ScanResultCard(
        partial: _scanState == IdScanState.partialResult,
        warnings: _scanWarnings,
        onRetake: _retake,
      );
    }
    if (_scanFailed) {
      return _ScanFailureCard(
        message: _scanMessage ?? context.tr('register.ocr_not_clear'),
        onRetake: _retake,
        onManual: _manualEntry,
      );
    }
    return _ScanPrompt(onScan: _startCapture, onManual: _manualEntry);
  }

  Widget _buildRegistrationForm(bool busy) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          context.tr('register.review_title'),
          style: SgType.cardHeading.copyWith(color: SgColors.textPrimary),
        ),
        const SizedBox(height: 14),
        SgTextField(
          label: context.tr('register.name'),
          controller: _name,
          icon: 'user-round',
          hint: context.tr('register.name_hint'),
          textInputAction: TextInputAction.next,
          autofillHints: const [AutofillHints.name],
          error: _nameErr,
        ),
        const SizedBox(height: 14),
        Directionality(
          textDirection: TextDirection.ltr,
          child: SgTextField(
            label: context.tr('register.nid'),
            controller: _nid,
            icon: 'shield',
            hint: context.tr('register.nid_hint'),
            keyboardType: TextInputType.number,
            textInputAction: TextInputAction.next,
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(14),
            ],
            error: _nidErr,
          ),
        ),
        const SizedBox(height: 14),
        SgTextField(
          label: context.tr('register.address'),
          controller: _address,
          icon: 'house',
          hint: context.tr('register.address_hint'),
          textInputAction: TextInputAction.next,
          autofillHints: const [AutofillHints.fullStreetAddress],
          error: _addressErr,
        ),
        if (_derived.isNotEmpty) ...[
          const SizedBox(height: 10),
          _DerivedPreview(values: _derived),
        ],
        const SizedBox(height: 22),
        Text(
          context.tr('register.finish_title'),
          style: SgType.cardHeading.copyWith(color: SgColors.textPrimary),
        ),
        const SizedBox(height: 14),
        SgTextField(
          label: context.tr('register.phone'),
          controller: _phone,
          icon: 'phone',
          hint: context.tr('register.phone_hint'),
          keyboardType: TextInputType.phone,
          textInputAction: TextInputAction.next,
          inputFormatters: [
            FilteringTextInputFormatter.digitsOnly,
            LengthLimitingTextInputFormatter(11),
          ],
          autofillHints: const [AutofillHints.telephoneNumber],
          error: _phoneErr,
        ),
        const SizedBox(height: 14),
        SgTextField(
          label: context.tr('register.pin'),
          controller: _pin,
          icon: 'shield',
          hint: context.tr('register.pin_hint'),
          obscure: true,
          keyboardType: TextInputType.number,
          textInputAction: TextInputAction.next,
          inputFormatters: [
            FilteringTextInputFormatter.digitsOnly,
            LengthLimitingTextInputFormatter(8),
          ],
          error: _pinErr,
        ),
        const SizedBox(height: 14),
        SgTextField(
          label: context.tr('register.pin_confirm'),
          controller: _pinConfirm,
          icon: 'shield',
          hint: context.tr('register.pin_hint'),
          obscure: true,
          keyboardType: TextInputType.number,
          textInputAction: TextInputAction.done,
          inputFormatters: [
            FilteringTextInputFormatter.digitsOnly,
            LengthLimitingTextInputFormatter(8),
          ],
          error: _pinConfirmErr,
        ),
        const SizedBox(height: 14),
        _LocationPicker(
          state: _locState,
          onTap: _locState == _LocState.capturing ? null : _useCurrentLocation,
        ),
        const SizedBox(height: 8),
        Text(
          context.tr('register.address_note'),
          style: const TextStyle(
            fontSize: 11,
            color: SgColors.textMuted,
            height: 1.4,
          ),
        ),
        const SizedBox(height: 24),
        SgPrimaryButton(
          key: const Key('register_submit'),
          label: context.tr('register.submit'),
          full: true,
          size: SgButtonSize.lg,
          loading: busy,
          onPressed: busy ? null : () => _submit(busy),
        ),
        const SizedBox(height: 14),
        Center(
          child: GestureDetector(
            onTap: busy ? null : Navigator.of(context).pop,
            child: Text.rich(
              TextSpan(
                text: '${context.tr('register.have_account')} ',
                style: SgType.caption.copyWith(color: SgColors.textMuted),
                children: [
                  TextSpan(
                    text: context.tr('register.login_link'),
                    style: SgType.caption.copyWith(
                      color: SgColors.infoStrong,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _ScanPrompt extends StatelessWidget {
  const _ScanPrompt({required this.onScan, required this.onManual});
  final VoidCallback onScan;
  final VoidCallback onManual;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: SgColors.bgSurface,
        borderRadius: BorderRadius.circular(SgRadius.card),
        border: Border.all(color: SgColors.blue200),
        boxShadow: SgShadows.card,
      ),
      child: Column(
        children: [
          Container(
            width: 52,
            height: 52,
            decoration: BoxDecoration(
              color: SgColors.infoSoft,
              borderRadius: BorderRadius.circular(SgRadius.control),
            ),
            child: const Center(
              child: SgIcon('shield', size: 26, color: SgColors.infoStrong),
            ),
          ),
          const SizedBox(height: 14),
          Text(
            context.tr('register.scan_title'),
            style: SgType.cardHeading.copyWith(color: SgColors.textPrimary),
          ),
          const SizedBox(height: 6),
          Text(
            context.tr('register.scan_body'),
            textAlign: TextAlign.center,
            style: SgType.caption.copyWith(color: SgColors.textMuted),
          ),
          const SizedBox(height: 18),
          SgPrimaryButton(
            key: const Key('scan_id'),
            label: context.tr('register.scan_cta'),
            icon: 'camera',
            full: true,
            onPressed: onScan,
          ),
          const SizedBox(height: 12),
          TextButton(
            onPressed: onManual,
            child: Text(context.tr('register.manual')),
          ),
        ],
      ),
    );
  }
}

class _ScanInstructions extends StatelessWidget {
  const _ScanInstructions();

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.fromLTRB(24, 24, 24, 18),
        decoration: const BoxDecoration(
          color: SgColors.bgSurface,
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(SgRadius.sheet),
          ),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              context.tr('register.instructions_title'),
              style: SgType.cardHeading.copyWith(color: SgColors.textPrimary),
            ),
            const SizedBox(height: 14),
            for (final key in [
              'register.tip_full',
              'register.tip_light',
              'register.tip_glare',
              'register.tip_flat',
              'register.tip_sharp',
            ])
              Padding(
                padding: const EdgeInsets.only(bottom: 7),
                child: Text('• ${context.tr(key)}', style: SgType.body),
              ),
            const SizedBox(height: 14),
            SgPrimaryButton(
              label: context.tr('register.open_camera'),
              icon: 'camera',
              full: true,
              onPressed: () => Navigator.of(context).pop(true),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: Text(context.tr('common.cancel')),
            ),
          ],
        ),
      ),
    );
  }
}

class _ImagePreview extends StatelessWidget {
  const _ImagePreview({
    required this.path,
    required this.onRetake,
    required this.onUse,
  });
  final String path;
  final VoidCallback onRetake;
  final VoidCallback onUse;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: SgColors.bgSurface,
        borderRadius: BorderRadius.circular(SgRadius.card),
        border: Border.all(color: SgColors.blue200),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(SgRadius.control),
            child: SizedBox(
              height: 180,
              child: Image.file(
                File(path),
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) => const ColoredBox(
                  color: SgColors.infoSoft,
                  child: Center(
                    child: SgIcon(
                      'shield',
                      size: 42,
                      color: SgColors.infoStrong,
                    ),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: SgSecondaryButton(
                  label: context.tr('register.retake'),
                  onPressed: onRetake,
                  full: true,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: SgPrimaryButton(
                  label: context.tr('register.use_photo'),
                  onPressed: onUse,
                  full: true,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ScanningCard extends StatelessWidget {
  const _ScanningCard();
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: SgColors.bgSurface,
        borderRadius: BorderRadius.circular(SgRadius.card),
        border: Border.all(color: SgColors.blue200),
      ),
      child: Column(
        children: [
          const CircularProgressIndicator(color: SgColors.infoStrong),
          const SizedBox(height: 16),
          Text(context.tr('register.reading'), style: SgType.cardHeading),
          const SizedBox(height: 4),
          Text(
            context.tr('register.reading_hint'),
            style: SgType.caption.copyWith(color: SgColors.textMuted),
          ),
        ],
      ),
    );
  }
}

class _ScanResultCard extends StatelessWidget {
  const _ScanResultCard({
    required this.partial,
    required this.warnings,
    required this.onRetake,
  });
  final bool partial;
  final List<String> warnings;
  final VoidCallback onRetake;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: SgColors.infoSoft,
        borderRadius: BorderRadius.circular(SgRadius.card),
        border: Border.all(color: SgColors.blue200),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SgIcon('shield-check', size: 24, color: SgColors.infoStrong),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  context.tr('register.scan_success'),
                  style: SgType.bodyMedium.copyWith(
                    color: SgColors.textPrimary,
                  ),
                ),
                Text(
                  context.tr(
                    partial
                        ? 'register.review_partial'
                        : 'register.review_body',
                  ),
                  style: SgType.caption.copyWith(color: SgColors.textMuted),
                ),
                for (final warning in warnings)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(
                      warning,
                      style: SgType.caption.copyWith(
                        color: SgColors.textSecondary,
                      ),
                    ),
                  ),
              ],
            ),
          ),
          TextButton(
            onPressed: onRetake,
            child: Text(context.tr('register.retake_short')),
          ),
        ],
      ),
    );
  }
}

class _ScanFailureCard extends StatelessWidget {
  const _ScanFailureCard({
    required this.message,
    required this.onRetake,
    required this.onManual,
  });
  final String message;
  final VoidCallback onRetake;
  final VoidCallback onManual;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: SgColors.emergencySoft,
        borderRadius: BorderRadius.circular(SgRadius.card),
        border: Border.all(color: SgColors.emergencyBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            message,
            style: SgType.body.copyWith(color: SgColors.emergencyHover),
          ),
          const SizedBox(height: 14),
          SgPrimaryButton(
            label: context.tr('register.retake'),
            icon: 'camera',
            full: true,
            onPressed: onRetake,
          ),
          const SizedBox(height: 8),
          TextButton(
            onPressed: onManual,
            child: Text(context.tr('register.manual')),
          ),
        ],
      ),
    );
  }
}

class _DerivedPreview extends StatelessWidget {
  const _DerivedPreview({required this.values});
  final Map<String, String> values;

  @override
  Widget build(BuildContext context) {
    final labels = {
      'birth_date': context.tr('register.birth_date'),
      'governorate': context.tr('register.governorate'),
      'gender': context.tr('register.gender'),
    };
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final entry in values.entries)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
            decoration: BoxDecoration(
              color: SgColors.infoSoft,
              borderRadius: BorderRadius.circular(SgRadius.pill),
            ),
            child: Text(
              '${labels[entry.key]}: ${entry.value}',
              style: SgType.caption,
            ),
          ),
      ],
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.onBack});
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 4),
      child: Align(
        alignment: AlignmentDirectional.centerStart,
        child: IconButton(
          tooltip: MaterialLocalizations.of(context).backButtonTooltip,
          onPressed: onBack,
          icon: const SgIcon(
            'arrow-left',
            size: 22,
            color: SgColors.textPrimary,
          ),
        ),
      ),
    );
  }
}

class _LocationPicker extends StatelessWidget {
  const _LocationPicker({required this.state, required this.onTap});
  final _LocState state;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final (icon, label, tone) = switch (state) {
      _LocState.saved => (
        'map-pin',
        context.tr('register.location_saved'),
        SgColors.infoStrong,
      ),
      _LocState.capturing => (
        'navigation',
        context.tr('register.location_capturing'),
        SgColors.textMuted,
      ),
      _LocState.failed => (
        'refresh-cw',
        context.tr('register.location_failed'),
        SgColors.emergencyHover,
      ),
      _LocState.idle => (
        'navigation',
        context.tr('register.use_location'),
        SgColors.textPrimary,
      ),
    };
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: SgColors.bgSurface,
          borderRadius: BorderRadius.circular(SgRadius.control),
          border: Border.all(
            color: state == _LocState.saved
                ? SgColors.infoStrong
                : SgColors.borderHairline,
            width: 1.5,
          ),
        ),
        child: Row(
          children: [
            if (state == _LocState.capturing)
              const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: SgColors.textMuted,
                ),
              )
            else
              SgIcon(icon, size: 18, color: tone),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                label,
                style: SgType.bodyMedium.copyWith(
                  color: tone,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner(this.message);
  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: SgColors.emergencySoft,
        borderRadius: BorderRadius.circular(SgRadius.control),
        border: Border.all(color: SgColors.emergencyBorder),
      ),
      child: Text(
        message,
        style: SgType.caption.copyWith(color: SgColors.emergencyHover),
      ),
    );
  }
}
