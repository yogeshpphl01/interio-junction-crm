/// Runtime configuration. Override the base URL at launch with
/// `--dart-define=IJ_API_BASE=https://api.yourhost.com/api`.
class IjConfig {
  const IjConfig({required this.baseUrl});

  final String baseUrl;

  /// Default targets the Android-emulator host loopback; override per environment.
  static const IjConfig fromEnv = IjConfig(
    baseUrl: String.fromEnvironment(
      'IJ_API_BASE',
      defaultValue: 'http://10.0.2.2:8000/api',
    ),
  );
}
