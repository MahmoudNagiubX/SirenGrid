import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sirengrid_citizen/core/api_client.dart';
import 'package:sirengrid_citizen/core/localization/locale_cubit.dart';
import 'package:sirengrid_citizen/core/services.dart';
import 'package:sirengrid_citizen/main.dart';

void main() {
  testWidgets('SirenGrid Citizen App smoke test (Arabic platform locale)', (WidgetTester tester) async {
    StorageService.enableMockStorage();
    LocaleCubit.overridePlatformLocale = const Locale('ar');
    addTearDown(() {
      LocaleCubit.overridePlatformLocale = null;
      StorageService.resetStorage();
    });

    await tester.pumpWidget(SirenGridCitizenApp(apiClient: ApiClient()));
    await tester.pumpAndSettle();

    // Default locale for Arabic platform is Arabic RTL
    expect(find.text('سايرنجريد'), findsOneWidget);
    expect(find.text('(SirenGrid)'), findsOneWidget);
    expect(find.text('تسجيل الدخول'), findsAtLeastNWidgets(1));
  });

  testWidgets('SirenGrid Citizen App smoke test (English platform locale)', (WidgetTester tester) async {
    StorageService.enableMockStorage();
    LocaleCubit.overridePlatformLocale = const Locale('en');
    addTearDown(() {
      LocaleCubit.overridePlatformLocale = null;
      StorageService.resetStorage();
    });

    await tester.pumpWidget(SirenGridCitizenApp(apiClient: ApiClient()));
    await tester.pumpAndSettle();

    // Default locale for English platform is English LTR
    expect(find.text('SirenGrid'), findsOneWidget);
    expect(find.text('Sign In'), findsAtLeastNWidgets(1));
  });
}
