import 'package:flutter/material.dart';
import '../../core/theme.dart';

// ponytail: single authoritative source of truth for emergency services across Home and Confirmation
enum EmergencyServiceType {
  ambulance,
  fire,
  police,
  general,
}

class EmergencyService {
  final EmergencyServiceType type;
  final String id;
  final String titleKey;
  final String subtitleKey;
  final String confirmBtnKey;
  final IconData icon;
  final String? svgPath;
  final Color fromColor;
  final Color toColor;
  final Color surfaceColor;
  final Color confirmButtonColor;

  const EmergencyService({
    required this.type,
    required this.id,
    required this.titleKey,
    required this.subtitleKey,
    required this.confirmBtnKey,
    required this.icon,
    this.svgPath,
    required this.fromColor,
    required this.toColor,
    required this.surfaceColor,
    required this.confirmButtonColor,
  });

  /// Authoritative icon renderer supporting both Flutter IconData and canonical vector paths
  Widget buildIcon({required Color color, double size = 24}) {
    if (svgPath != null) {
      return CanonicalVectorIcon(
        key: Key('service_icon_$id'),
        svgPath: svgPath!,
        size: size,
        color: color,
      );
    }
    return Icon(
      icon,
      key: Key('service_icon_$id'),
      size: size,
      color: color,
    );
  }

  static const List<EmergencyService> all = [
    EmergencyService(
      type: EmergencyServiceType.ambulance,
      id: 'ambulance',
      titleKey: 'home.service_ambulance',
      subtitleKey: 'home.service_ambulance_sub',
      confirmBtnKey: 'confirm.submit_ambulance',
      icon: Icons.add_rounded,
      svgPath:
          'M19 10.5h-5.5V5c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v5.5H5c-.83 0-1.5.67-1.5 1.5s.67 1.5 1.5 1.5h5.5V19c0 .83.67 1.5 1.5 1.5s1.5-.67 1.5-1.5v-5.5H19c.83 0 1.5-.67 1.5-1.5s-.67-1.5-1.5-1.5z',
      fromColor: AppColors.ambulanceFrom, // #EF233C
      toColor: AppColors.ambulanceTo, // #D90429
      surfaceColor: AppColors.ambulanceBg, // #FFF1F2
      confirmButtonColor: AppColors.ambulanceTo, // #D90429
    ),
    EmergencyService(
      type: EmergencyServiceType.fire,
      id: 'fire',
      titleKey: 'home.service_fire',
      subtitleKey: 'home.service_fire_sub',
      confirmBtnKey: 'confirm.submit_fire',
      icon: Icons.whatshot_rounded,
      svgPath:
          'M12 23c-4.97 0-9-4.03-9-9 0-4.63 3.49-8.45 8-8.95V4c0-.55.45-1 1-1 .3 0 .58.14.77.37 2.97 3.63 4.23 6.94 4.23 9.63 0 5.52-4.48 10-10 10zm0-16.89c-3.87.49-6.9 3.75-6.9 7.89 0 4.36 3.54 7.9 7.9 7.9s7.9-3.54 7.9-7.9c0-2.31-1.12-5.18-3.72-8.39-.77.94-1.89 1.54-3.18 1.54-.55 0-1-.45-1-1 0-.39.11-.75.3-1.04H12z',
      fromColor: AppColors.fireFrom, // #FB923C
      toColor: AppColors.fireTo, // #EA580C
      surfaceColor: AppColors.fireBg, // #FFF7ED
      confirmButtonColor: AppColors.fireTo, // #EA580C
    ),
    EmergencyService(
      type: EmergencyServiceType.police,
      id: 'police',
      titleKey: 'home.service_police',
      subtitleKey: 'home.service_police_sub',
      confirmBtnKey: 'confirm.submit_police',
      icon: Icons.shield_outlined,
      svgPath:
          'M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm7 10c0 4.52-3.11 8.76-7 9.93-3.89-1.17-7-5.41-7-9.93V6.3l7-3.11 7 3.11V11z',
      fromColor: AppColors.policeFrom, // #3B82F6
      toColor: AppColors.policeTo, // #1D4ED8
      surfaceColor: AppColors.policeBg, // #EFF6FF
      confirmButtonColor: AppColors.policeTo, // #1D4ED8
    ),
    EmergencyService(
      type: EmergencyServiceType.general,
      id: 'general',
      titleKey: 'home.service_general',
      subtitleKey: 'home.service_general_sub',
      confirmBtnKey: 'confirm.submit_general',
      icon: Icons.warning_rounded,
      svgPath:
          'M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z',
      fromColor: AppColors.generalFrom, // #14B8A6
      toColor: AppColors.generalTo, // #0F766E
      surfaceColor: AppColors.generalBg, // #F0FDFA
      confirmButtonColor: AppColors.generalTo, // #0F766E
    ),
  ];

  static EmergencyService findById(String id) {
    return all.firstWhere(
      (s) => s.id == id.toLowerCase(),
      orElse: () => all.first,
    );
  }

  static EmergencyService findByType(EmergencyServiceType type) {
    return all.firstWhere((s) => s.type == type, orElse: () => all.first);
  }

  // ponytail: explicit centralized mapping between UI presentation services and backend frozen API enum
  // Allowed backend values per Master Plan 14.1: AMBULANCE | FIRE | POLICE | GENERAL
  String get backendServiceCode {
    switch (type) {
      case EmergencyServiceType.ambulance:
        return 'AMBULANCE';
      case EmergencyServiceType.fire:
        return 'FIRE';
      case EmergencyServiceType.police:
        return 'POLICE';
      case EmergencyServiceType.general:
        return 'GENERAL';
    }
  }

  static EmergencyService fromBackendCode(String code) {
    switch (code.trim().toUpperCase()) {
      case 'AMBULANCE':
        return findByType(EmergencyServiceType.ambulance);
      case 'FIRE':
        return findByType(EmergencyServiceType.fire);
      case 'POLICE':
        return findByType(EmergencyServiceType.police);
      case 'GENERAL':
      default:
        return findByType(EmergencyServiceType.general);
    }
  }
}

/// Minimal native vector icon painter rendering canonical SVG paths
class CanonicalVectorIcon extends StatelessWidget {
  final String svgPath;
  final double size;
  final Color color;

  const CanonicalVectorIcon({
    super.key,
    required this.svgPath,
    this.size = 24.0,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size(size, size),
      painter: _CanonicalVectorPainter(
        svgPath: svgPath,
        color: color,
      ),
    );
  }
}

class _CanonicalVectorPainter extends CustomPainter {
  final String svgPath;
  final Color color;
  static final Map<String, Path> _pathCache = {};

  _CanonicalVectorPainter({
    required this.svgPath,
    required this.color,
  });

  Path _getPath() {
    return _pathCache.putIfAbsent(svgPath, () => parseSvgPathData(svgPath));
  }

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.fill;

    canvas.save();
    canvas.scale(size.width / 24.0, size.height / 24.0);
    canvas.drawPath(_getPath(), paint);
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _CanonicalVectorPainter oldDelegate) =>
      oldDelegate.color != color || oldDelegate.svgPath != svgPath;
}

/// Lightweight parser for 24x24 SVG path definitions
Path parseSvgPathData(String d) {
  final path = Path()..fillType = PathFillType.evenOdd;
  final regExp = RegExp(r'([a-zA-Z])|([-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?)');
  final matches = regExp.allMatches(d);

  double curX = 0;
  double curY = 0;
  double startX = 0;
  double startY = 0;
  double lastCpX = 0;
  double lastCpY = 0;
  String currentCmd = '';
  final args = <double>[];

  void flushCmd() {
    if (currentCmd.isEmpty) return;
    int i = 0;
    while (i < args.length || (currentCmd.toLowerCase() == 'z' && i == 0)) {
      switch (currentCmd) {
        case 'M':
          curX = args[i++];
          curY = args[i++];
          startX = curX;
          startY = curY;
          lastCpX = curX;
          lastCpY = curY;
          path.moveTo(curX, curY);
          currentCmd = 'L';
          break;
        case 'm':
          curX += args[i++];
          curY += args[i++];
          startX = curX;
          startY = curY;
          lastCpX = curX;
          lastCpY = curY;
          path.moveTo(curX, curY);
          currentCmd = 'l';
          break;
        case 'L':
          curX = args[i++];
          curY = args[i++];
          path.lineTo(curX, curY);
          lastCpX = curX;
          lastCpY = curY;
          break;
        case 'l':
          curX += args[i++];
          curY += args[i++];
          path.lineTo(curX, curY);
          lastCpX = curX;
          lastCpY = curY;
          break;
        case 'H':
          curX = args[i++];
          path.lineTo(curX, curY);
          lastCpX = curX;
          lastCpY = curY;
          break;
        case 'h':
          curX += args[i++];
          path.lineTo(curX, curY);
          lastCpX = curX;
          lastCpY = curY;
          break;
        case 'V':
          curY = args[i++];
          path.lineTo(curX, curY);
          lastCpX = curX;
          lastCpY = curY;
          break;
        case 'v':
          curY += args[i++];
          path.lineTo(curX, curY);
          lastCpX = curX;
          lastCpY = curY;
          break;
        case 'C':
          final x1 = args[i++];
          final y1 = args[i++];
          final x2 = args[i++];
          final y2 = args[i++];
          curX = args[i++];
          curY = args[i++];
          path.cubicTo(x1, y1, x2, y2, curX, curY);
          lastCpX = x2;
          lastCpY = y2;
          break;
        case 'c':
          final x1 = curX + args[i++];
          final y1 = curY + args[i++];
          final x2 = curX + args[i++];
          final y2 = curY + args[i++];
          curX += args[i++];
          curY += args[i++];
          path.cubicTo(x1, y1, x2, y2, curX, curY);
          lastCpX = x2;
          lastCpY = y2;
          break;
        case 'S':
          final x1 = 2 * curX - lastCpX;
          final y1 = 2 * curY - lastCpY;
          final x2 = args[i++];
          final y2 = args[i++];
          curX = args[i++];
          curY = args[i++];
          path.cubicTo(x1, y1, x2, y2, curX, curY);
          lastCpX = x2;
          lastCpY = y2;
          break;
        case 's':
          final x1 = 2 * curX - lastCpX;
          final y1 = 2 * curY - lastCpY;
          final x2 = curX + args[i++];
          final y2 = curY + args[i++];
          curX += args[i++];
          curY += args[i++];
          path.cubicTo(x1, y1, x2, y2, curX, curY);
          lastCpX = x2;
          lastCpY = y2;
          break;
        case 'Z':
        case 'z':
          path.close();
          curX = startX;
          curY = startY;
          lastCpX = curX;
          lastCpY = curY;
          i++;
          break;
        default:
          i++;
          break;
      }
    }
    args.clear();
  }

  for (final match in matches) {
    final cmd = match.group(1);
    final numStr = match.group(2);
    if (cmd != null) {
      flushCmd();
      currentCmd = cmd;
    } else if (numStr != null) {
      args.add(double.parse(numStr));
    }
  }
  flushCmd();
  return path;
}

