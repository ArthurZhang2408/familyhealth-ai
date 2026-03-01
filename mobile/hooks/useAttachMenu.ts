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

/** Convert HEIC/HEIF (or any unsupported format) to JPEG for backend + Gemini compatibility. */
async function ensureJpeg(uri: string, mimeType: string | null | undefined, fallbackName: string): Promise<Attachment> {
  const mime = mimeType?.toLowerCase() ?? '';
  const needsConversion = mime.includes('heic') || mime.includes('heif') || uri.toLowerCase().endsWith('.heic') || uri.toLowerCase().endsWith('.heif');

  if (needsConversion) {
    const result = await manipulateAsync(uri, [], { format: SaveFormat.JPEG, compress: 0.8 });
    return {
      uri: result.uri,
      name: fallbackName.replace(/\.heic$|\.heif$/i, '.jpg'),
      type: 'image/jpeg',
    };
  }

  return { uri, name: fallbackName, type: mime || 'image/jpeg' };
}

/**
 * Returns a function that shows a Camera / Photos / Files action sheet.
 * The picked attachment is passed to the `onPicked` callback.
 * HEIC images are auto-converted to JPEG on the client.
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
    const attachment = await ensureJpeg(
      asset.uri,
      asset.mimeType,
      asset.fileName ?? `photo_${Date.now()}.jpg`,
    );
    onPicked(attachment);
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
    const attachment = await ensureJpeg(
      asset.uri,
      asset.mimeType,
      asset.fileName ?? `image_${Date.now()}.jpg`,
    );
    onPicked(attachment);
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
