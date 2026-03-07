import { ActionSheetIOS, Platform, Alert } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import { manipulateAsync, SaveFormat } from 'expo-image-manipulator';
import * as Haptics from 'expo-haptics';

export interface Attachment {
  uri: string;
  name: string;
  type: string;
}

const ALLOWED_IMAGE_TYPES = new Set([
  'image/jpeg',
  'image/jpg',
  'image/png',
  'image/webp',
]);

const MAX_DIMENSION = 1536;
const COMPRESS_QUALITY = 0.7;

/** Validate MIME type. Returns error message or null if valid. */
function validateType(mimeType: string | null | undefined, fileName: string): string | null {
  const mime = mimeType?.toLowerCase() ?? '';
  // HEIC/HEIF will be converted to JPEG — always allowed
  if (mime.includes('heic') || mime.includes('heif')) return null;
  // PDFs allowed for file picker
  if (mime === 'application/pdf') return null;
  if (ALLOWED_IMAGE_TYPES.has(mime)) return null;
  // Check extension as fallback
  const ext = fileName.toLowerCase().split('.').pop();
  if (ext && ['jpg', 'jpeg', 'png', 'webp', 'heic', 'heif'].includes(ext)) return null;
  return `Unsupported file type: ${mime || ext || 'unknown'}. Use JPEG, PNG, or WebP images.`;
}

/** Convert HEIC/HEIF to JPEG and compress/resize large images. */
async function processImage(
  uri: string,
  mimeType: string | null | undefined,
  fallbackName: string,
): Promise<Attachment> {
  const mime = mimeType?.toLowerCase() ?? '';
  const isHeic =
    mime.includes('heic') || mime.includes('heif') ||
    uri.toLowerCase().endsWith('.heic') || uri.toLowerCase().endsWith('.heif');

  // Always compress and resize to keep uploads fast
  const result = await manipulateAsync(
    uri,
    [{ resize: { width: MAX_DIMENSION } }],
    { format: SaveFormat.JPEG, compress: COMPRESS_QUALITY },
  );

  const name = isHeic
    ? fallbackName.replace(/\.heic$|\.heif$/i, '.jpg')
    : fallbackName;

  return { uri: result.uri, name, type: 'image/jpeg' };
}

/**
 * Returns a function that shows a Camera / Photos / Files action sheet.
 * The picked attachment is passed to the `onPicked` callback.
 * Unsupported file types are rejected immediately with an Alert.
 * Images are compressed and resized to max 1536px before upload.
 */
export function useAttachMenu(onPicked: (attachment: Attachment) => void) {
  const pickCamera = async () => {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      Alert.alert('Permission needed', 'Camera access is required to take a photo.');
      return;
    }
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ['images'],
      quality: 0.8,
    });
    if (result.canceled || !result.assets?.[0]) return;
    const asset = result.assets[0];
    try {
      const attachment = await processImage(
        asset.uri,
        asset.mimeType,
        asset.fileName ?? `photo_${Date.now()}.jpg`,
      );
      onPicked(attachment);
    } catch {
      Alert.alert('Error', 'Could not process the photo. Please try again.');
    }
  };

  const pickPhotos = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert('Permission needed', 'Photo library access is required.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.8,
    });
    if (result.canceled || !result.assets?.[0]) return;
    const asset = result.assets[0];

    const error = validateType(asset.mimeType, asset.fileName ?? '');
    if (error) {
      Alert.alert('Unsupported format', error);
      return;
    }

    try {
      const attachment = await processImage(
        asset.uri,
        asset.mimeType,
        asset.fileName ?? `image_${Date.now()}.jpg`,
      );
      onPicked(attachment);
    } catch {
      Alert.alert('Error', 'Could not process the image. Please try again.');
    }
  };

  const pickFile = async () => {
    const result = await DocumentPicker.getDocumentAsync({
      type: ['application/pdf', 'image/jpeg', 'image/png', 'image/webp'],
      copyToCacheDirectory: true,
    });
    if (result.canceled || !result.assets?.[0]) return;
    const asset = result.assets[0];
    onPicked({
      uri: asset.uri,
      name: asset.name,
      type: asset.mimeType ?? 'application/pdf',
    });
  };

  return () => {
    if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    if (Platform.OS === 'ios') {
      ActionSheetIOS.showActionSheetWithOptions(
        {
          options: ['Camera', 'Photos', 'Files', 'Cancel'],
          cancelButtonIndex: 3,
        },
        (index) => {
          if (index === 0) pickCamera();
          else if (index === 1) pickPhotos();
          else if (index === 2) pickFile();
        },
      );
    } else {
      Alert.alert('Attach', undefined, [
        { text: 'Camera', onPress: pickCamera },
        { text: 'Photos', onPress: pickPhotos },
        { text: 'Files', onPress: pickFile },
        { text: 'Cancel', style: 'cancel' },
      ]);
    }
  };
}
