import 'package:flutter/material.dart';

import '../../l10n/strings.dart';
import '../sg_icon.dart';
import '../tokens.dart';

/// Exactly three destinations (brief §17). A small red dot marks Track when a
/// request is active — never a fourth tab, never a Notifications tab.
class SgBottomNavigation extends StatelessWidget {
  const SgBottomNavigation({
    super.key,
    required this.currentIndex,
    required this.onTap,
    this.activeRequest = false,
  });

  final int currentIndex;
  final ValueChanged<int> onTap;
  final bool activeRequest;

  static const _items = [
    (icon: 'house', key: 'nav.home'),
    (icon: 'map', key: 'nav.track'),
    (icon: 'user-round', key: 'nav.account'),
  ];

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: SgColors.bgSurface,
        borderRadius: BorderRadius.circular(SgRadius.sheet),
        boxShadow: SgShadows.float,
      ),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          for (var i = 0; i < _items.length; i++)
            _NavButton(
              icon: _items[i].icon,
              label: context.tr(_items[i].key),
              active: currentIndex == i,
              badge: i == 1 && activeRequest,
              onTap: () => onTap(i),
            ),
        ],
      ),
    );
  }
}

class _NavButton extends StatelessWidget {
  const _NavButton({
    required this.icon,
    required this.label,
    required this.active,
    required this.badge,
    required this.onTap,
  });

  final String icon;
  final String label;
  final bool active;
  final bool badge;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: active,
      label: label,
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: Container(
          constraints: const BoxConstraints(minWidth: SgSpace.touchMin),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 6),
          child: Stack(
            clipBehavior: Clip.none,
            children: [
              Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SgIcon(
                    icon,
                    size: 22,
                    color: active ? SgColors.emergency : SgColors.textMuted,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    label,
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: active ? FontWeight.w600 : FontWeight.w400,
                      color: active ? SgColors.navy900 : SgColors.textMuted,
                    ),
                  ),
                ],
              ),
              if (badge) const Positioned(top: 0, right: -2, child: _Dot()),
            ],
          ),
        ),
      ),
    );
  }
}

class _Dot extends StatelessWidget {
  const _Dot();
  @override
  Widget build(BuildContext context) => Container(
    width: 7,
    height: 7,
    decoration: const BoxDecoration(
      color: SgColors.emergency,
      shape: BoxShape.circle,
    ),
  );
}

/// Floating bottom-sheet shell — drag handle, rounded top corners, soft shadow,
/// slide-up entrance (340ms, emphasized easing).
class SgBottomSheet extends StatelessWidget {
  const SgBottomSheet({super.key, required this.child, this.withHandle = true});

  final Widget child;
  final bool withHandle;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: const BoxDecoration(
        color: SgColors.bgSurface,
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(SgRadius.sheet),
        ),
        boxShadow: SgShadows.sheet,
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (withHandle)
              Padding(
                padding: const EdgeInsets.only(top: 12, bottom: 2),
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: SgColors.borderStrong,
                    borderRadius: BorderRadius.circular(SgRadius.pill),
                  ),
                ),
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(22, 16, 22, 26),
              child: child,
            ),
          ],
        ),
      ),
    );
  }

  /// Shows [child] wrapped in this shell as a modal with the design's scrim
  /// (navy 44%) and slide-up motion.
  static Future<T?> show<T>(
    BuildContext context, {
    required Widget child,
    bool dismissible = true,
  }) {
    return showModalBottomSheet<T>(
      context: context,
      isScrollControlled: true,
      isDismissible: dismissible,
      enableDrag: dismissible,
      barrierColor: const Color(0x702B2D42),
      backgroundColor: Colors.transparent,
      transitionAnimationController: null,
      builder: (_) => SgBottomSheet(child: child),
    );
  }
}
