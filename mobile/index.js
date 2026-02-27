// Polyfills must run before any other module is evaluated.
// Importing here guarantees they execute before expo-router loads anything.
import './polyfills/crypto';
import 'expo-router/entry';
