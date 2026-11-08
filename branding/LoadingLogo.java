package nova.branding;

import java.io.IOException;
import java.io.InputStream;
import java.util.Base64;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

/** Supplies Nova's startup texture to the 1.21.11 Fabric loading overlay. */
public final class LoadingLogo implements ClassFileTransformer {
    private static final String OVERLAY = "net/minecraft/class_425$class_4070";
    private static final String RESOURCES = "net/minecraft/class_5912";
    private static final String LOGO = loadLogo();

    public static void premain(String ignored, Instrumentation instrumentation) {
        instrumentation.addTransformer(new LoadingLogo());
    }

    private static String loadLogo() {
        try (InputStream image = LoadingLogo.class.getResourceAsStream("/nova/branding/logo.png")) {
            return Base64.getEncoder().encodeToString(image.readAllBytes());
        } catch (IOException error) {
            throw new IllegalStateException("No se pudo leer el logo de Nova", error);
        }
    }

    @Override
    public byte[] transform(ClassLoader loader, String name, Class<?> type,
                            ProtectionDomain domain, byte[] bytes) {
        if (!OVERLAY.equals(name)) {
            return null;
        }
        ClassReader reader = new ClassReader(bytes);
        ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
        reader.accept(new ClassVisitor(Opcodes.ASM9, writer) {
            @Override
            public MethodVisitor visitMethod(int access, String method, String descriptor,
                                             String signature, String[] exceptions) {
                return new MethodVisitor(Opcodes.ASM9,
                        super.visitMethod(access, method, descriptor, signature, exceptions)) {
                    @Override
                    public void visitMethodInsn(int opcode, String owner, String called,
                                                String signature, boolean isInterface) {
                        if (opcode == Opcodes.INVOKEINTERFACE && RESOURCES.equals(owner)
                                && "(Lnet/minecraft/class_2960;)Ljava/io/InputStream;".equals(signature)) {
                            super.visitInsn(Opcodes.POP2);
                            super.visitTypeInsn(Opcodes.NEW, "java/io/ByteArrayInputStream");
                            super.visitInsn(Opcodes.DUP);
                            super.visitMethodInsn(Opcodes.INVOKESTATIC, "java/util/Base64",
                                                  "getDecoder", "()Ljava/util/Base64$Decoder;", false);
                            super.visitLdcInsn(LOGO);
                            super.visitMethodInsn(Opcodes.INVOKEVIRTUAL, "java/util/Base64$Decoder",
                                                  "decode", "(Ljava/lang/String;)[B", false);
                            super.visitMethodInsn(Opcodes.INVOKESPECIAL, "java/io/ByteArrayInputStream",
                                                  "<init>", "([B)V", false);
                            System.out.println("[Nova] Textura de carga aplicada");
                        } else {
                            super.visitMethodInsn(opcode, owner, called, signature, isInterface);
                        }
                    }
                };
            }
        }, 0);
        return writer.toByteArray();
    }
}
