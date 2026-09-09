import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../sg_icon.dart';
import '../tokens.dart';

/// Labeled input for Login (phone / PIN). Flexible width for RTL/Arabic labels
/// (brief §8) — no fixed-width label column.
class SgTextField extends StatefulWidget {
  const SgTextField({
    super.key,
    required this.label,
    this.controller,
    this.icon,
    this.hint,
    this.obscure = false,
    this.keyboardType,
    this.inputFormatters,
    this.error,
    this.textInputAction,
    this.onSubmitted,
    this.autofillHints,
  });

  final String label;
  final TextEditingController? controller;
  final String? icon;
  final String? hint;
  final bool obscure;
  final TextInputType? keyboardType;
  final List<TextInputFormatter>? inputFormatters;
  final String? error;
  final TextInputAction? textInputAction;
  final ValueChanged<String>? onSubmitted;
  final List<String>? autofillHints;

  @override
  State<SgTextField> createState() => _SgTextFieldState();
}

class _SgTextFieldState extends State<SgTextField> {
  final _focus = FocusNode();
  bool _reveal = false;

  @override
  void initState() {
    super.initState();
    _focus.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final borderColor = widget.error != null
        ? SgColors.emergency
        : _focus.hasFocus
        ? SgColors.infoStrong
        : SgColors.borderHairline;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          widget.label,
          style: SgType.captionMedium.copyWith(color: SgColors.textSecondary),
        ),
        const SizedBox(height: 8),
        AnimatedContainer(
          duration: SgDur.fast,
          height: SgSpace.touchMin,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          decoration: BoxDecoration(
            color: SgColors.bgSurface,
            borderRadius: BorderRadius.circular(SgRadius.control),
            border: Border.all(color: borderColor, width: 1.5),
            boxShadow: _focus.hasFocus
                ? const [
                    BoxShadow(
                      color: SgColors.focusRing,
                      blurRadius: 0,
                      spreadRadius: 3,
                    ),
                  ]
                : null,
          ),
          child: Row(
            children: [
              if (widget.icon != null) ...[
                SgIcon(widget.icon!, size: 19, color: SgColors.textMuted),
                const SizedBox(width: 10),
              ],
              Expanded(
                child: TextField(
                  controller: widget.controller,
                  focusNode: _focus,
                  obscureText: widget.obscure && !_reveal,
                  keyboardType: widget.keyboardType,
                  inputFormatters: widget.inputFormatters,
                  textInputAction: widget.textInputAction,
                  onSubmitted: widget.onSubmitted,
                  autofillHints: widget.autofillHints,
                  style: SgType.body.copyWith(color: SgColors.textPrimary),
                  cursorColor: SgColors.infoStrong,
                  decoration: InputDecoration(
                    isCollapsed: true,
                    border: InputBorder.none,
                    hintText: widget.hint,
                    hintStyle: SgType.body.copyWith(color: SgColors.textMuted),
                  ),
                ),
              ),
              if (widget.obscure)
                Semantics(
                  button: true,
                  label: _reveal ? 'Hide PIN' : 'Show PIN',
                  child: GestureDetector(
                    onTap: () => setState(() => _reveal = !_reveal),
                    behavior: HitTestBehavior.opaque,
                    child: Padding(
                      padding: const EdgeInsets.only(left: 8),
                      child: SgIcon(
                        _reveal ? 'eye-off' : 'eye',
                        size: 19,
                        color: _reveal
                            ? SgColors.infoStrong
                            : SgColors.textMuted,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
        if (widget.error != null) ...[
          const SizedBox(height: 6),
          Text(
            widget.error!,
            style: SgType.caption.copyWith(color: SgColors.emergencyHover),
          ),
        ],
      ],
    );
  }
}

/// One row in Account's permission list. Trailing = granted badge or Allow btn.
class SgPermissionRow extends StatelessWidget {
  const SgPermissionRow({
    super.key,
    required this.icon,
    required this.label,
    required this.granted,
    this.description,
    this.grantedLabel = 'Granted',
    this.actionLabel = 'Allow',
    this.onAction,
  });

  final String icon;
  final String label;
  final bool granted;
  final String? description;
  final String grantedLabel;
  final String actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 4),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: SgColors.borderHairline)),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: SgColors.bgSunken,
              borderRadius: BorderRadius.circular(SgRadius.control),
            ),
            child: Center(
              child: SgIcon(icon, size: 20, color: SgColors.navy900),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: SgType.bodyMedium.copyWith(
                    color: SgColors.textPrimary,
                  ),
                ),
                if (description != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      description!,
                      style: SgType.caption.copyWith(color: SgColors.textMuted),
                    ),
                  ),
              ],
            ),
          ),
          if (granted)
            Row(
              children: [
                const SgIcon(
                  'shield-check',
                  size: 16,
                  color: SgColors.infoStrong,
                ),
                const SizedBox(width: 6),
                Text(
                  grantedLabel,
                  style: SgType.captionMedium.copyWith(
                    color: SgColors.infoStrong,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            )
          else
            GestureDetector(
              onTap: onAction,
              child: Container(
                height: 34,
                padding: const EdgeInsets.symmetric(horizontal: 14),
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: SgColors.navy900,
                  borderRadius: BorderRadius.circular(SgRadius.pill),
                ),
                child: Text(
                  actionLabel,
                  style: SgType.captionMedium.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
