import { View, ActivityIndicator } from 'react-native';
import { Colors } from '@/constants/colors';

export function LoadingSpinner() {
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
      <ActivityIndicator size="large" color={Colors.primary} />
    </View>
  );
}
