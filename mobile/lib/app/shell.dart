import 'package:flutter/material.dart';
import '../core/localization/siren_localizations.dart';
import '../core/services.dart';
import '../core/theme.dart';
import '../features/account/account_screen.dart';
import '../features/alerts/alert_banner.dart';
import '../features/emergency_home/emergency_service.dart';
import '../features/emergency_home/home_screen.dart';
import '../features/tracking/tracking_screen.dart';

// ponytail: canonical 3-tab MainShell matching the locked prototype exactly
class MainShell extends StatefulWidget {
  final bool enableSubmissionFlow;
  final ValueChanged<EmergencyService>? onEmergencyConfirmed;

  const MainShell({
    super.key,
    this.enableSubmissionFlow = true,
    this.onEmergencyConfirmed,
  });

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _currentIndex = 0;
  String? _activeEmergencyRequestId;
  late final PageController _pageController;

  @override
  void initState() {
    super.initState();
    _pageController = PageController(initialPage: _currentIndex);
    _loadActiveRequestId();
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  Future<void> _loadActiveRequestId() async {
    final activeId = await StorageService.getActiveRequestId();
    if (activeId != null && mounted) {
      setState(() {
        _activeEmergencyRequestId = activeId;
      });
    }
  }

  void _handleEmergencySubmitted(String requestId) {
    setState(() {
      _activeEmergencyRequestId = requestId;
      _currentIndex = 1; // Authoritative transition to Tracking tab
    });
    if (_pageController.hasClients) {
      _pageController.animateToPage(
        1,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeInOutCubic,
      );
    }
  }

  void _navigateToTab(int index) {
    setState(() => _currentIndex = index);
    if (_pageController.hasClients) {
      _pageController.animateToPage(
        index,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeInOutCubic,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    final screens = [
      HomeScreen(
        onEmergencyConfirmed: widget.onEmergencyConfirmed,
        onEmergencySubmitted: widget.enableSubmissionFlow ? _handleEmergencySubmitted : null,
      ),
      TrackingScreen(
        initialRequestId: _activeEmergencyRequestId,
        onReturnHome: () => _navigateToTab(0),
      ),
      const AccountScreen(),
    ];

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        child: Column(
          children: [
            const CorridorAlertBanner(), // Clear-the-Way alert banner atop app
            Expanded(
              child: PageView(
                controller: _pageController,
                physics: const NeverScrollableScrollPhysics(),
                children: screens,
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: colors.surface,
          border: Border(
            top: BorderSide(color: colors.border, width: 1),
          ),
        ),
        child: BottomNavigationBar(
          currentIndex: _currentIndex,
          backgroundColor: colors.surface,
          selectedItemColor: context.isDark ? AppColors.accentBlue : AppColors.primary,
          unselectedItemColor: colors.textMuted,
          selectedFontSize: 12,
          unselectedFontSize: 12,
          selectedLabelStyle: const TextStyle(fontWeight: FontWeight.w600),
          unselectedLabelStyle: const TextStyle(fontWeight: FontWeight.w500),
          type: BottomNavigationBarType.fixed,
          elevation: 0,
          onTap: _navigateToTab,
          items: [
            BottomNavigationBarItem(
              icon: const Icon(Icons.emergency_outlined),
              activeIcon: const Icon(Icons.emergency),
              label: context.tr('nav.home'),
            ),
            BottomNavigationBarItem(
              icon: const Icon(Icons.location_searching_outlined),
              activeIcon: const Icon(Icons.location_searching),
              label: context.tr('nav.track'),
            ),
            BottomNavigationBarItem(
              icon: const Icon(Icons.person_outline),
              activeIcon: const Icon(Icons.person),
              label: context.tr('nav.account'),
            ),
          ],
        ),
      ),
    );
  }
}
