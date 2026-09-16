package com.ssafy.witw.domain.user.entity;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Getter
@Entity
@Table(name = "users")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 255)
    private String email;

    @Column(name = "password_hash", length = 255)
    private String passwordHash;

    @Enumerated(EnumType.STRING)
    @Column(name = "auth_provider", nullable = false, length = 20)
    private AuthProvider authProvider;

    @Column(name = "provider_id", length = 255)
    private String providerId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private UserRole role;

    @Column(name = "withdrawn_at")
    private LocalDateTime withdrawnAt;

    public boolean isWithdrawn(){
        return withdrawnAt != null;
    }

    public void withdraw(){
        withdrawnAt = LocalDateTime.now();
    }



    public static User createLocal(String email, String passwordHash){
        User user = new User();

        user.email = email;
        user.passwordHash = passwordHash;
        user.authProvider = AuthProvider.LOCAL;
        user.role = UserRole.USER;

        return user;
    }

    public void reactivateLocal(String passwordHash){
        this.passwordHash = passwordHash;
        this.authProvider = AuthProvider.LOCAL;
        this.providerId = null;
        this.role = UserRole.USER;
        this.withdrawnAt = null;
    }

    public void changePassword(String passwordHash){
        this.passwordHash = passwordHash;
    }
}
