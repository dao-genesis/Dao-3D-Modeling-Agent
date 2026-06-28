import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { MeshoptDecoder } from 'meshoptimizer';

const inPath = process.argv[2] || '../tripo_model.glb';
const outPath = process.argv[3] || '../tripo_decoded.glb';

await MeshoptDecoder.ready;

const io = new NodeIO()
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({ 'meshopt.decoder': MeshoptDecoder });

const doc = await io.read(inPath);

// strip meshopt extension so output is plain/uncompressed
const root = doc.getRoot();
for (const ext of root.listExtensionsUsed()) {
  if (ext.extensionName === 'EXT_meshopt_compression') ext.dispose();
}

let nMesh = 0, nPrim = 0, nVert = 0, nTri = 0;
for (const mesh of root.listMeshes()) {
  nMesh++;
  for (const prim of mesh.listPrimitives()) {
    nPrim++;
    const pos = prim.getAttribute('POSITION');
    if (pos) nVert += pos.getCount();
    const idx = prim.getIndices();
    if (idx) nTri += idx.getCount() / 3;
  }
}
console.log('meshes', nMesh, 'prims', nPrim, 'verts', nVert, 'tris', nTri);

const plainIO = new NodeIO();
await plainIO.write(outPath, doc);
console.log('WROTE', outPath);
