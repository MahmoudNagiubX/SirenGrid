import 'package:flutter/material.dart';
import '../../../core/localization/siren_localizations.dart';
import '../../../core/theme.dart';
import '../emergency_service.dart';

// ponytail: reusable native card widget driven by authoritative EmergencyService metadata
class EmergencyServiceCard extends StatelessWidget {
  final EmergencyService service;
  final VoidCallback onTap;

  const EmergencyServiceCard({
    super.key,
    required this.service,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    const cardRadius = 20.0;

    return Container(
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(cardRadius),
        border: Border.all(
          color: context.isDark ? colors.border : colors.border.withValues(alpha: 0.6),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: context.isDark ? 0.25 : 0.04),
            blurRadius: 16,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(cardRadius),
        child: InkWell(
          key: Key('service_card_${service.id}'),
          onTap: onTap,
          borderRadius: BorderRadius.circular(cardRadius),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 22, horizontal: 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.center,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // Semantic Icon Badge
                Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [service.fromColor, service.toColor],
                    ),
                    borderRadius: BorderRadius.circular(16),
                    boxShadow: [
                      BoxShadow(
                        color: service.toColor.withValues(alpha: 0.3),
                        blurRadius: 10,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: Center(
                    child: service.buildIcon(
                      color: Colors.white,
                      size: 28,
                    ),
                  ),
                ),
                const SizedBox(height: 14),

                // Localized Service Title
                Text(
                  context.tr(service.titleKey),
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.w700,
                    color: colors.textPrimary,
                  ),
                ),
                const SizedBox(height: 4),

                // Localized Service Subtitle
                Text(
                  context.tr(service.subtitleKey),
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 12.5,
                    fontWeight: FontWeight.w400,
                    color: colors.textMuted,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
