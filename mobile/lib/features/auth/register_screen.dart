import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../core/config.dart';
import '../../core/localization/locale_cubit.dart';
import '../../core/localization/siren_localizations.dart';
import '../../core/theme.dart';

// ponytail: native Flutter RegisterScreen matching locked prototype register.html
// UI + local validation only; reports BACKEND CONTRACT GAP — CITIZEN REGISTRATION
class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _nameController = TextEditingController();
  final _phoneController = TextEditingController();
  final _nidController = TextEditingController();
  final _pinController = TextEditingController();

  String? _validationError;

  @override
  void dispose() {
    _nameController.dispose();
    _phoneController.dispose();
    _nidController.dispose();
    _pinController.dispose();
    super.dispose();
  }

  void _handleSubmit(bool isArabic) {
    final name = _nameController.text.trim();
    final phone = _phoneController.text.trim();
    final nid = _nidController.text.trim();
    final pin = _pinController.text.trim();

    if (name.isEmpty) {
      setState(() {
        _validationError = isArabic ? 'يرجى إدخال الاسم بالكامل' : 'Please enter your full name';
      });
      return;
    }
    if (phone.isEmpty) {
      setState(() {
        _validationError = isArabic ? 'يرجى إدخال رقم الهاتف' : 'Please enter your phone number';
      });
      return;
    }
    if (nid.length != 14) {
      setState(() {
        _validationError = isArabic
            ? 'يجب أن يتكون الرقم القومي من 14 رقماً'
            : 'National ID must be exactly 14 digits';
      });
      return;
    }
    if (pin.length != 4) {
      setState(() {
        _validationError = isArabic
            ? 'يجب أن يتكون رمز PIN من 4 أرقام'
            : 'PIN must be exactly 4 digits';
      });
      return;
    }

    setState(() {
      _validationError = null;
    });

    // Truthful message: registration backend endpoint is not implemented yet
    final message = isArabic
        ? 'خدمة إنشاء الحساب غير متصلة بالخادم بعد.'
        : 'Registration backend is not connected yet.';

    ScaffoldMessenger.of(context).hideCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        key: const Key('register_feedback_snackbar'),
        content: Text(message),
        backgroundColor: AppColors.primaryNavy,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isArabic = context.watch<LocaleCubit>().isArabic;
    final colors = context.colors;

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        child: CustomScrollView(
          physics: const ClampingScrollPhysics(),
          slivers: [
            SliverFillRemaining(
              hasScrollBody: false,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const SizedBox(height: 8),
                        // Brand Header
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Wrap(
                              crossAxisAlignment: WrapCrossAlignment.center,
                              spacing: 6,
                              children: [
                                Text(
                                  context.tr('brand.name'),
                                  style: TextStyle(
                                    fontSize: 24,
                                    fontWeight: FontWeight.w700,
                                    color: colors.textPrimary,
                                  ),
                                ),
                                if (isArabic)
                                  Text(
                                    context.tr('brand.name_en'),
                                    style: TextStyle(
                                      fontSize: 16,
                                      fontWeight: FontWeight.w400,
                                      color: colors.textMuted,
                                    ),
                                  ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Text(
                              context.tr('brand.tagline'),
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w400,
                                color: colors.textMuted,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 28),

                        // Section Title & Subtitle
                        Text(
                          context.tr('register.title'),
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w700,
                            color: colors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          context.tr('register.subtitle'),
                          style: TextStyle(
                            fontSize: 13,
                            color: colors.textMuted,
                            height: 1.5,
                          ),
                        ),
                        const SizedBox(height: 24),

                        // Validation Error Alert
                        if (_validationError != null) ...[
                          Container(
                            key: const Key('register_validation_error'),
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                            decoration: BoxDecoration(
                              color: AppColors.emergencyLight,
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: AppColors.emergencyBorder),
                            ),
                            child: Row(
                              children: [
                                const Icon(Icons.error_outline, size: 16, color: AppColors.emergencyStrong),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    _validationError!,
                                    style: const TextStyle(
                                      fontSize: 12,
                                      fontWeight: FontWeight.w500,
                                      color: AppColors.emergencyStrong,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 16),
                        ],

                        // Full Name Field
                        Text(
                          context.tr('register.name_label'),
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: colors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 6),
                        TextField(
                          key: const Key('register_name_input'),
                          controller: _nameController,
                          textCapitalization: TextCapitalization.words,
                          style: TextStyle(fontSize: 14, color: colors.textPrimary),
                          decoration: InputDecoration(
                            hintText: isArabic ? 'منى عادل فاروق' : 'Mona Adel Farouk',
                          ),
                        ),
                        const SizedBox(height: 16),

                        // Phone Number Field (Always LTR)
                        Text(
                          context.tr('register.phone_label'),
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: colors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Directionality(
                          textDirection: TextDirection.ltr,
                          child: TextField(
                            key: const Key('register_phone_input'),
                            controller: _phoneController,
                            keyboardType: TextInputType.phone,
                            style: TextStyle(fontSize: 14, color: colors.textPrimary),
                            decoration: const InputDecoration(
                              hintText: '+20 10 000 0000',
                            ),
                          ),
                        ),
                        const SizedBox(height: 16),

                        // National ID Field (14 digits max, numeric, LTR)
                        Text(
                          context.tr('register.nid_label'),
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: colors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Directionality(
                          textDirection: TextDirection.ltr,
                          child: TextField(
                            key: const Key('register_nid_input'),
                            controller: _nidController,
                            keyboardType: TextInputType.number,
                            maxLength: 14,
                            inputFormatters: [
                              FilteringTextInputFormatter.digitsOnly,
                              LengthLimitingTextInputFormatter(14),
                            ],
                            style: TextStyle(
                              fontSize: 14,
                              letterSpacing: 1.5,
                              color: colors.textPrimary,
                            ),
                            decoration: InputDecoration(
                              counterText: '',
                              hintText: isArabic
                                  ? 'الرقم القومي المكون من 14 رقم'
                                  : '14-digit National ID',
                            ),
                          ),
                        ),
                        const SizedBox(height: 16),

                        // 4-Digit Security PIN Field (Obscured, numeric, LTR)
                        Text(
                          context.tr('register.pin_label'),
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: colors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Directionality(
                          textDirection: TextDirection.ltr,
                          child: TextField(
                            key: const Key('register_pin_input'),
                            controller: _pinController,
                            obscureText: true,
                            keyboardType: TextInputType.number,
                            maxLength: 4,
                            inputFormatters: [
                              FilteringTextInputFormatter.digitsOnly,
                              LengthLimitingTextInputFormatter(4),
                            ],
                            style: TextStyle(
                              fontSize: 14,
                              letterSpacing: 4.0,
                              color: colors.textPrimary,
                            ),
                            decoration: const InputDecoration(
                              counterText: '',
                              hintText: '••••',
                            ),
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          context.tr('register.pin_hint'),
                          style: TextStyle(
                            fontSize: 11,
                            color: colors.textMuted,
                          ),
                        ),
                        const SizedBox(height: 24),

                        // Submit CTA Button
                        ElevatedButton(
                          key: const Key('register_submit_button'),
                          onPressed: () => _handleSubmit(isArabic),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: context.isDark ? AppColors.accentBlue : AppColors.primary,
                            foregroundColor: Colors.white,
                            minimumSize: const Size.fromHeight(48),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(AppRadii.button),
                            ),
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(
                                context.tr('register.submit'),
                                style: const TextStyle(
                                  fontSize: 15,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              const SizedBox(width: 8),
                              Icon(
                                isArabic ? Icons.arrow_back_rounded : Icons.arrow_forward_rounded,
                                size: 18,
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 16),

                        // Back to Sign In Link
                        Center(
                          child: Wrap(
                            alignment: WrapAlignment.center,
                            crossAxisAlignment: WrapCrossAlignment.center,
                            spacing: 4,
                            children: [
                              Text(
                                context.tr('register.have_account'),
                                style: TextStyle(
                                  fontSize: 13,
                                  color: colors.textMuted,
                                ),
                              ),
                              GestureDetector(
                                key: const Key('register_signin_link'),
                                onTap: () => Navigator.of(context).pop(),
                                child: Text(
                                  context.tr('register.signin_link'),
                                  style: TextStyle(
                                    fontSize: 13,
                                    fontWeight: FontWeight.w600,
                                    color: context.isDark ? AppColors.accentBlue : AppColors.primary,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),

                    // Emergency Direct Call Footer
                    Padding(
                      padding: const EdgeInsets.only(top: 32, bottom: 8),
                      child: Container(
                        padding: const EdgeInsets.only(top: 20),
                        decoration: BoxDecoration(
                          border: Border(
                            top: BorderSide(color: colors.border, width: 1),
                          ),
                        ),
                        child: Text.rich(
                          TextSpan(
                            style: TextStyle(
                              fontSize: 12,
                              color: colors.textMuted,
                              height: 1.5,
                            ),
                            children: [
                              TextSpan(
                                text: isArabic
                                    ? 'في حالة الخطر المباشر؟ اتصل برقم '
                                    : 'Immediate danger? Call ',
                              ),
                              TextSpan(
                                text: AppConfig.hotlinePolice,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w700,
                                  color: AppColors.emergencyStrong,
                                ),
                              ),
                              TextSpan(
                                text: isArabic
                                    ? ' مباشرة — لا يلزم تسجيل الدخول.'
                                    : ' directly — no account needed.',
                              ),
                            ],
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
