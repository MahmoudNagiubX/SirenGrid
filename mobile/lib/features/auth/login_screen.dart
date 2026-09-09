import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../core/config.dart';
import '../../core/localization/locale_cubit.dart';
import '../../core/localization/siren_localizations.dart';
import '../../core/theme.dart';
import 'auth_cubit.dart';
import 'register_screen.dart';

// ponytail: single consolidated LoginScreen handling both Arabic RTL and English LTR without duplicate layouts
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  // ponytail: do NOT prefill credentials in production code
  final _phoneController = TextEditingController();
  final _pinController = TextEditingController();

  @override
  void dispose() {
    _phoneController.dispose();
    _pinController.dispose();
    super.dispose();
  }

  void _handleSubmit(BuildContext context) {
    final phone = _phoneController.text.trim();
    final pin = _pinController.text.trim();
    context.read<AuthCubit>().loginWithPhoneAndPin(phone, pin);
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

                        // Brand Header (Wrap prevents horizontal RenderFlex overflow on narrow widths)
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
                        const SizedBox(height: 32),

                        // Sign-In Section Title
                        Text(
                          context.tr('signin.title'),
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w700,
                            color: colors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          context.tr('signin.subtitle'),
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w400,
                            color: colors.textMuted,
                          ),
                        ),
                      const SizedBox(height: 24),

                      // Auth State Feedback Banner (Inline error representation)
                      BlocBuilder<AuthCubit, AuthState>(
                        builder: (context, state) {
                          if (state is AuthFailure && !state.isSessionCheckFailure) {
                            return Container(
                              key: const Key('login_error_banner'),
                              margin: const EdgeInsets.only(bottom: 20),
                              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                              decoration: BoxDecoration(
                                color: AppColors.emergencyLight,
                                border: Border.all(color: AppColors.emergencyBorder),
                                borderRadius: BorderRadius.circular(AppRadii.input),
                              ),
                              child: Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Icon(Icons.error_outline, size: 20, color: AppColors.emergencyStrong),
                                  const SizedBox(width: 10),
                                  Expanded(
                                    child: Text(
                                      state.message,
                                      style: const TextStyle(
                                        fontSize: 13,
                                        color: AppColors.emergencyStrong,
                                        fontWeight: FontWeight.w500,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            );
                          }
                          return const SizedBox.shrink();
                        },
                      ),

                      // Phone Number Field (Strictly LTR digit entry)
                      Text(
                        context.tr('signin.phone_label'),
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w500,
                          color: colors.textPrimary,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Directionality(
                        textDirection: TextDirection.ltr,
                        child: TextField(
                          key: const Key('login_phone_field'),
                          controller: _phoneController,
                          keyboardType: TextInputType.phone,
                          textInputAction: TextInputAction.next,
                          style: TextStyle(fontSize: 14, color: colors.textPrimary),
                          decoration: const InputDecoration(
                            hintText: '+20 10 000 0000',
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),

                      // PIN Code Field (Strictly LTR numeric entry, obscured)
                      Text(
                        context.tr('signin.pin_label'),
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w500,
                          color: colors.textPrimary,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Directionality(
                        textDirection: TextDirection.ltr,
                        child: TextField(
                          key: const Key('login_pin_field'),
                          controller: _pinController,
                          keyboardType: TextInputType.number,
                          inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                          obscureText: true,
                          maxLength: 4,
                          textInputAction: TextInputAction.done,
                          onSubmitted: (_) => _handleSubmit(context),
                          style: TextStyle(fontSize: 14, color: colors.textPrimary),
                          decoration: const InputDecoration(
                            hintText: '••••',
                            counterText: '',
                          ),
                        ),
                      ),
                      const SizedBox(height: 20),

                      // Submit CTA Button (Minimum 48px height, duplicate submit prevention)
                      BlocBuilder<AuthCubit, AuthState>(
                        builder: (context, state) {
                          final isLoading = state is Authenticating;

                          return ElevatedButton(
                            key: const Key('login_submit_button'),
                            onPressed: isLoading ? null : () => _handleSubmit(context),
                            style: ElevatedButton.styleFrom(
                              minimumSize: const Size.fromHeight(AppDimensions.buttonHeight),
                              backgroundColor: AppColors.primary,
                              foregroundColor: Colors.white,
                              disabledBackgroundColor: AppColors.primary.withValues(alpha: 0.6),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(AppRadii.button),
                              ),
                            ),
                            child: isLoading
                                ? const SizedBox(
                                    width: 20,
                                    height: 20,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                    ),
                                  )
                                : Row(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Flexible(
                                        child: Text(
                                          context.tr('signin.submit'),
                                          overflow: TextOverflow.ellipsis,
                                          style: const TextStyle(
                                            fontSize: 15,
                                            fontWeight: FontWeight.w600,
                                            color: Colors.white,
                                          ),
                                        ),
                                      ),
                                      const SizedBox(width: 8),
                                      Transform.scale(
                                        scaleX: isArabic ? -1.0 : 1.0,
                                        child: const Icon(
                                          Icons.arrow_forward,
                                          size: 18,
                                          color: Colors.white,
                                        ),
                                      ),
                                    ],
                                  ),
                          );
                        },
                      ),
                      const SizedBox(height: 18),

                      // Forgot PIN / Contact Center Help Link
                      Center(
                        child: Wrap(
                          alignment: WrapAlignment.center,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          spacing: 4,
                          children: [
                            Text(
                              context.tr('signin.forgot_pin'),
                              style: TextStyle(
                                fontSize: 13,
                                color: colors.textMuted,
                              ),
                            ),
                            Text(
                              context.tr('signin.contact_center'),
                              style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w500,
                                color: colors.textPrimary,
                                decoration: TextDecoration.underline,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 14),

                      // Don't have an account? Register link
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
                              key: const Key('login_register_link'),
                              onTap: () {
                                Navigator.of(context).push(
                                  MaterialPageRoute(builder: (_) => const RegisterScreen()),
                                );
                              },
                              child: Text(
                                context.tr('register.title'),
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

                      // Development-Only UI Preview Entry (Strictly guarded by AppConfig.isPreviewAllowed)
                      if (AppConfig.isPreviewAllowed) ...[
                        const SizedBox(height: 20),
                        Center(
                          child: OutlinedButton.icon(
                            key: const Key('login_preview_button'),
                            onPressed: () => context.read<AuthCubit>().enterPreviewMode(),
                            icon: const Icon(Icons.visibility_outlined, size: 16),
                            label: Text(
                              context.tr('signin.preview_btn'),
                              style: const TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            style: OutlinedButton.styleFrom(
                              minimumSize: const Size(200, 36),
                              foregroundColor: const Color(0xFFD97706),
                              side: const BorderSide(color: Color(0xFFFCD34D)),
                              backgroundColor: const Color(0xFFFFFBEB),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(AppRadii.button),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ],
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
