import {
  AlertTriangle,
  Calendar,
  Check,
  Clock,
  Download,
  ExternalLink,
  Eye,
  FileArchive,
  FileDown,
  FileSignature,
  FileText,
  FolderArchive,
  FolderDown,
  MapPin,
  Package,
  RefreshCw,
  Trash2,
  Upload,
  Zap,
  type IconNode,
} from "lucide";

export type IconName =
  | "AlertTriangle"
  | "Calendar"
  | "Check"
  | "Clock"
  | "Download"
  | "ExternalLink"
  | "Eye"
  | "FileArchive"
  | "FileDown"
  | "FileSignature"
  | "FileText"
  | "FolderArchive"
  | "FolderDown"
  | "MapPin"
  | "Package"
  | "RefreshCw"
  | "Trash2"
  | "Upload"
  | "Zap";

const ICONS: Record<IconName, IconNode> = {
  AlertTriangle,
  Calendar,
  Check,
  Clock,
  Download,
  ExternalLink,
  Eye,
  FileArchive,
  FileDown,
  FileSignature,
  FileText,
  FolderArchive,
  FolderDown,
  MapPin,
  Package,
  RefreshCw,
  Trash2,
  Upload,
  Zap,
};

export interface IconOptions {
  size?: number;
  strokeWidth?: number;
  className?: string;
  ariaHidden?: boolean;
}

/**
 * Returns an inline SVG string for the requested Lucide icon.
 * Zero-DOM parsing overhead, fully tree-shaken and SSR/test safe.
 */
export function renderIcon(name: IconName, options: IconOptions = {}): string {
  const node = ICONS[name];
  if (!node) return "";
  const size = options.size ?? 14;
  const strokeWidth = options.strokeWidth ?? 2;
  const className = options.className ? ` class="${options.className}"` : "";
  const aria = options.ariaHidden !== false ? ' aria-hidden="true"' : "";

  const children = node
    .map(([tag, attrs]) => {
      const attrStr = Object.entries(attrs)
        .map(([k, v]) => `${k}="${v}"`)
        .join(" ");
      return `<${tag} ${attrStr}/>`;
    })
    .join("");

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round"${className}${aria}>${children}</svg>`;
}
