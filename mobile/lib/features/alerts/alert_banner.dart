import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/services.dart';
import '../../core/theme.dart';

// ponytail: single standalone widget polls active corridor alert & renders warning overlay
class CorridorAlertBanner extends StatefulWidget {
  const CorridorAlertBanner({super.key});

  @override
  State<CorridorAlertBanner> createState() => _CorridorAlertBannerState();
}

class _CorridorAlertBannerState extends State<CorridorAlertBanner> {
  Timer? _alertTimer;
  String? _activeAlertMessage;

  @override
  void initState() {
    super.initState();
    _startAlertCheck();
  }

  void _startAlertCheck() {
    // Poll active corridor alert every 20 seconds
    _checkAlert();
    _alertTimer = Timer.periodic(const Duration(seconds: 20), (_) => _checkAlert());
  }

  Future<void> _checkAlert() async {
    try {
      final pos = await LocationService.getCurrentLocation();
      final client = ApiClient();
      final res = await client.get('/api/v1/mobile/alerts/active?lat=${pos.latitude}&lon=${pos.longitude}');
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        if (data != null && data['active'] == true) {
          if (mounted) {
            setState(() {
              _activeAlertMessage = data['message'] ?? 'Emergency vehicle approaching. Please keep the route clear.';
            });
          }
          return;
        }
      }
    } catch (_) {
      // Ignored for calm error handling
    }
  }

  @override
  void dispose() {
    _alertTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_activeAlertMessage == null) return const SizedBox.shrink();

    return Container(
      width: double.infinity,
      color: AppColors.emergencyRed,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Row(
        children: [
          const Icon(Icons.warning_amber_rounded, color: Colors.white, size: 28),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text(
                  'CLEAR THE WAY ALERT',
                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13),
                ),
                Text(
                  _activeAlertMessage!,
                  style: const TextStyle(color: Colors.white, fontSize: 12),
                ),
              ],
            ),
          ),
          IconButton(
            icon: const Icon(Icons.close, color: Colors.white, size: 20),
            onPressed: () => setState(() => _activeAlertMessage = null),
          ),
        ],
      ),
    );
  }
}
