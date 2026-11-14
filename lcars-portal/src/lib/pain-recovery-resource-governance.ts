import { resourceLibrary } from './pain-recovery-resource-library';

export function resourceHealthReport(){return resourceLibrary.map(resource=>({id:resource.id,url:resource.url,https:resource.url.startsWith('https://'),reviewed:resource.reviewed,metadataComplete:Boolean(resource.format&&resource.energy&&resource.accessibility&&resource.duration)}));}
export function allResourcesGoverned(){return resourceHealthReport().every(resource=>resource.https&&resource.metadataComplete&&Boolean(resource.reviewed));}
