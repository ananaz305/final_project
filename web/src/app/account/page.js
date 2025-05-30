'use client';

import React, {useState} from 'react';

import Box from "@mui/material/Box";
import {Menu} from "@/components/Menu/Menu";
import {useLoginContext} from "@/providers";
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import ListItemIcon from "@mui/material/ListItemIcon";
import CheckIcon from "@mui/icons-material/Check";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";

const Account = () => {
    const [isLoading, setLoading] = useState(false);

    const {user, setUser} = useLoginContext();

    return (
        <Box sx={{display: 'flex', width: '100%', height: '100%'}}>
            <Menu currentPage="account"/>
            <Box sx={{flexGrow: 1, position: 'relative', padding: 4}}>
                <img alt="union jack"
                     src="https://upload.wikimedia.org/wikipedia/commons/thumb/a/a5/Flag_of_the_United_Kingdom_%281-2%29.svg/1200px-Flag_of_the_United_Kingdom_%281-2%29.svg.png"
                     style={{
                         position: 'absolute',
                         width: '100%',
                         inset: 0,
                         objectFit: 'cover',
                         objectPosition: 'center',
                         opacity: '0.3'
                     }}
                />
                {user ? (
                    <List sx={{maxWidth: 340}}>
                        <ListItem disablePadding>
                            <ListItemButton>
                                <ListItemText secondary={user.firstName} primary="First Name"/>
                            </ListItemButton>
                        </ListItem>
                        <ListItem disablePadding>
                            <ListItemButton>
                                <ListItemText secondary={user.lastName} primary="Last Name"/>
                            </ListItemButton>
                        </ListItem>
                        <ListItem disablePadding>
                            <ListItemButton>
                                <ListItemText secondary={user.email} primary="Email"/>
                            </ListItemButton>
                        </ListItem>
                        {!user.nin?.verified && <ListItem disablePadding>
                            <ListItemButton>
                                <ListItemText
                                    secondary={
                                        <input
                                            value={user.nin?.value || ''}
                                            onChange={(e) => setUser(prevState => ({
                                                ...prevState,
                                                nin: {value: e.target.value}
                                            }))}
                                            disabled={isLoading || user.nin?.verified}
                                            style={{border: 'none', background: 'none', outline: 'none'}}
                                        />
                                    }
                                    primary="NIN"
                                />
                                {user.nin?.value && !user.nin?.verified && (
                                    <Button
                                        onClick={() => {
                                            setLoading(true);

                                            setTimeout(() => {
                                                setUser(prevState => ({
                                                    ...prevState,
                                                    nin: {...prevState.nin, verified: true}
                                                }))
                                            }, 3000)
                                        }}
                                        loading={isLoading}
                                    >
                                        submit
                                    </Button>
                                )}
                            </ListItemButton>
                        </ListItem>}
                    </List>
                ) : (
                    <Typography variant="h4">You need to login</Typography>
                )}
            </Box>
        </Box>
    );
}

export default Account;
