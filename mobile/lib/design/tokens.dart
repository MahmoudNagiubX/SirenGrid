import 'package:flutter/widgets.dart';

/// SirenGrid Citizen design tokens — a 1:1 port of the Claude Design handoff
/// (`tokens/*.css`, brief §4–§13). Values are exact.
class SgColors {
  const SgColors._();

  // Neutral ramp — white to Deep Navy
  static const gray0 = Color(0xFFF5F7F9);
  static const gray50 = Color(0xFFEDF2F4); // Light Mist / app background
  static const gray100 = Color(0xFFE4E9EE);
  static const gray200 = Color(0xFFD8DEE6); // hairline border
  static const gray300 = Color(0xFFC4CCD8);
  static const gray400 = Color(0xFFA6AFBF); // strong border
  static const gray500 = Color(0xFF8D99AE); // Slate Blue-Gray
  static const gray600 = Color(0xFF6B7688); // muted text
  static const gray700 = Color(0xFF4E5766);
  static const gray800 = Color(0xFF363C4C); // secondary text
  static const navy900 = Color(0xFF2B2D42); // Deep Navy / primary text
  static const navy950 = Color(0xFF1F2133); // headings / pressed structural

  // Support blue scale — map / tracking / informational
  static const blue50 = Color(0xFFF0F3FA);
  static const blue100 = Color(0xFFD5DEEF);
  static const blue200 = Color(0xFFB1C9EF);
  static const blue300 = Color(0xFF8AAEE0);
  static const blue400 = Color(0xFF638ECB);
  static const blue600 = Color(0xFF395886);

  // Emergency red ramp
  static const red50 = Color(0xFFFDEBEC);
  static const red100 = Color(0xFFFAD0D4);
  static const red200 = Color(0xFFF3909B);
  static const red300 = Color(0xFFF45C6C);
  static const red400 = Color(0xFFEF3C50);
  static const red500 = Color(0xFFEF233C); // Emergency Red
  static const red600 = Color(0xFFD90429); // Critical Red
  static const red700 = Color(0xFFA5081F);
  static const red800 = Color(0xFF7A0A1E);

  // Semantic
  static const bgApp = gray50;
  static const bgSurface = Color(0xFFFFFFFF);
  static const bgSunken = gray100;
  static const borderHairline = gray200;
  static const borderStrong = gray400;
  static const textPrimary = navy900;
  static const heading = navy950;
  static const textSecondary = gray800;
  static const textMuted = gray600;
  static const onNavy = Color(0xFFFFFFFF);

  static const emergency = red500;
  static const emergencyHover = red600;
  static const emergencySoft = red50;
  static const emergencyBorder = red200;
  static const critical = red600;
  static const emergencyGlow = Color(0x66D90429); // rgba(217,4,41,.40)

  static const info = blue400;
  static const infoSoft = blue50;
  static const infoStrong = blue600;
  static const route = blue600;
  static const routeHalo = blue200;

  // Map
  static const mapBg = Color(0xFFE3EAF6);
  static const mapRoute = blue600;
  static const mapRouteHalo = blue200;
  static const mapCitizenPin = red500;
  static const mapResponder = navy900;

  static const focusRing = blue200;

  // Gradients
  static const gradientHero = LinearGradient(
    begin: Alignment(-0.6, -1),
    end: Alignment(0.6, 1),
    colors: [Color(0xFFEF233C), Color(0xFFD90429), Color(0xFFB00423)],
    stops: [0.0, 0.62, 1.0],
  );
  static const gradientEmergency = LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: [Color(0xFFF4304A), Color(0xFFEF233C), Color(0xFFD90429)],
    stops: [0.0, 0.46, 1.0],
  );
}

class SgSpace {
  const SgSpace._();
  static const s1 = 4.0;
  static const s2 = 8.0;
  static const s3 = 12.0;
  static const s4 = 16.0;
  static const s6 = 24.0;
  static const s8 = 32.0;
  static const hero = 44.0;
  static const page = 22.0; // horizontal page padding
  static const touchMin = 48.0;
}

class SgRadius {
  const SgRadius._();
  static const control = 14.0;
  static const card = 22.0;
  static const cardLg = 26.0;
  static const sheet = 28.0;
  static const pill = 999.0;
}

class SgShadows {
  const SgShadows._();
  static const _tint = Color(0x1F1F2133); // navy-tinted, low opacity base

  static const xs = <BoxShadow>[
    BoxShadow(color: Color(0x121F2133), blurRadius: 2, offset: Offset(0, 1)),
    BoxShadow(color: Color(0x0D1F2133), blurRadius: 3, offset: Offset(0, 1)),
  ];
  static const card = <BoxShadow>[
    BoxShadow(color: Color(0x0D1F2133), blurRadius: 4, offset: Offset(0, 2)),
    BoxShadow(color: Color(0x1A1F2133), blurRadius: 30, offset: Offset(0, 12)),
  ];
  static const cardStrong = <BoxShadow>[
    BoxShadow(color: Color(0x121F2133), blurRadius: 8, offset: Offset(0, 4)),
    BoxShadow(color: Color(0x261F2133), blurRadius: 44, offset: Offset(0, 20)),
  ];
  static const sheet = <BoxShadow>[
    BoxShadow(color: Color(0x0D1F2133), blurRadius: 6, offset: Offset(0, -2)),
    BoxShadow(color: Color(0x2E1F2133), blurRadius: 44, offset: Offset(0, -16)),
  ];
  static const float = <BoxShadow>[
    BoxShadow(color: Color(0x1A1F2133), blurRadius: 14, offset: Offset(0, 6)),
    BoxShadow(color: Color(0x331F2133), blurRadius: 50, offset: Offset(0, 22)),
  ];
  static const marker = <BoxShadow>[
    BoxShadow(color: Color(0x291F2133), blurRadius: 4, offset: Offset(0, 2)),
    BoxShadow(color: Color(0x381F2133), blurRadius: 18, offset: Offset(0, 8)),
  ];
  static const ctaGlow = <BoxShadow>[
    BoxShadow(color: Color(0x1A1F2133), blurRadius: 6, offset: Offset(0, 2)),
    BoxShadow(
      color: SgColors.emergencyGlow,
      blurRadius: 30,
      offset: Offset(0, 12),
    ),
  ];
  static const emergencyStrong = <BoxShadow>[
    BoxShadow(color: Color(0x241F2133), blurRadius: 8, offset: Offset(0, 3)),
    BoxShadow(
      color: SgColors.emergencyGlow,
      blurRadius: 40,
      offset: Offset(0, 18),
    ),
  ];

  static const tint = _tint;
}

class SgDur {
  const SgDur._();
  static const fast = Duration(milliseconds: 120);
  static const base = Duration(milliseconds: 200);
  static const slow = Duration(milliseconds: 320);
  static const sheet = Duration(milliseconds: 340);
  static const easeEmphasized = Cubic(0.16, 0.84, 0.24, 1);
  static const easeStandard = Cubic(0.2, 0.7, 0.2, 1);
}

/// Type scale (brief §7 / `tokens/typography.css`). Font family is applied by
/// [sgTextTheme]; these are size/height/weight only so they compose with Rubik.
class SgType {
  const SgType._();
  static const display = TextStyle(
    fontSize: 32,
    height: 38 / 32,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.32,
  );
  static const title = TextStyle(
    fontSize: 26,
    height: 32 / 26,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.26,
  );
  static const cardHeading = TextStyle(
    fontSize: 17,
    height: 22 / 17,
    fontWeight: FontWeight.w600,
    letterSpacing: -0.17,
  );
  static const body = TextStyle(
    fontSize: 15,
    height: 22 / 15,
    fontWeight: FontWeight.w400,
  );
  static const bodyMedium = TextStyle(
    fontSize: 15,
    height: 22 / 15,
    fontWeight: FontWeight.w500,
  );
  static const caption = TextStyle(
    fontSize: 13,
    height: 18 / 13,
    fontWeight: FontWeight.w400,
  );
  static const captionMedium = TextStyle(
    fontSize: 13,
    height: 18 / 13,
    fontWeight: FontWeight.w500,
  );
  static const eta = TextStyle(
    fontSize: 28,
    height: 32 / 28,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.56,
  );
  static const chip = TextStyle(
    fontSize: 11,
    fontWeight: FontWeight.w700,
    letterSpacing: 0.66,
  ); // ~0.06em
}
