import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sirengrid_citizen/core/api_client.dart';

void main() {
  late File image;

  setUp(() async {
    image = File(
      '${Directory.systemTemp.path}${Platform.pathSeparator}sirengrid-ocr-test.jpg',
    );
    await image.writeAsBytes([0xff, 0xd8, 0xff, 0xd9], flush: true);
  });

  tearDown(() async {
    if (await image.exists()) await image.delete();
  });

  test('scanNationalId sends one front image to the canonical route', () async {
    final client = _MultipartClient(
      response: {
        'success': true,
        'extracted': {'national_id': '29001010123456'},
        'warnings': <String>[],
        'identity_source': 'EGYPTIAN_ID_OCR_DEMO',
      },
    );
    final api = ApiClient(client: client);

    final result = await api.scanNationalId(image.path);

    expect(result['success'], isTrue);
    expect(client.request!.url.path, endsWith('/auth/scan-national-id'));
    expect(client.request!.files.single.field, 'file');
    expect(client.request!.fields, isEmpty);
  });

  test(
    'scanNationalId maps timeout without changing normal API timeout',
    () async {
      final api = ApiClient(client: _NeverClient());

      final result = await api.scanNationalId(
        image.path,
        timeout: const Duration(milliseconds: 5),
      );

      expect(result['success'], isFalse);
      expect(result['code'], 'TIMEOUT');
    },
  );

  test('scanNationalId maps offline transport to a safe failure', () async {
    final api = ApiClient(client: _ThrowingClient());

    final result = await api.scanNationalId(image.path);

    expect(result['success'], isFalse);
    expect(result['code'], 'BACKEND_UNAVAILABLE');
  });

  test('scanNationalId unwraps safe upload validation errors', () async {
    final api = ApiClient(
      client: _MultipartClient(
        status: 413,
        response: {
          'detail': {
            'code': 'IMAGE_TOO_LARGE',
            'message': 'The image must be 10 MB or smaller.',
          },
        },
      ),
    );

    final result = await api.scanNationalId(image.path);

    expect(result['success'], isFalse);
    expect(result['code'], 'IMAGE_TOO_LARGE');
    expect(result['message'], contains('10 MB'));
  });
}

class _MultipartClient extends http.BaseClient {
  _MultipartClient({required this.response, this.status = 200});

  final Map<String, dynamic> response;
  final int status;
  http.MultipartRequest? request;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest base) async {
    request = base as http.MultipartRequest;
    await request!.finalize().drain<void>();
    return http.StreamedResponse(
      Stream.value(utf8.encode(jsonEncode(response))),
      status,
      headers: {'content-type': 'application/json'},
    );
  }
}

class _NeverClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) =>
      Completer<http.StreamedResponse>().future;
}

class _ThrowingClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async =>
      throw const SocketException('offline');
}
